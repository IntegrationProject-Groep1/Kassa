"""
receiver.py — RabbitMQ consumer for the Kassa integration service.

Connects to the broker defined by RABBIT_HOST/PORT/VHOST and listens on the
queue set by RABBIT_INCOMING_QUEUE (default: kassa.incoming).

Handles four incoming message types sent by the CRM / IoT teams:
    - new_registration     → creates or updates a res.partner in Odoo
    - profile_update       → updates name, email, age, VAT on an existing partner
    - badge_scanned        → looks up a customer by x_badge_id; sends a
                                                     system_error to kassa.errors if the badge is unknown
    - cancel_registration  → sets active=False on the partner (soft delete)

Error handling:
    - Unparseable XML          → basic_nack(requeue=False) + system_error sent
    - XSD validation failure   → basic_nack(requeue=False) + system_error sent
    - Unknown message type     → basic_nack(requeue=False) + system_error sent
    - Odoo connection/API error → basic_nack(requeue=True) + system_error sent
    - Duplicate message_id     → basic_ack, no Odoo write (silently ignored)

Duplicate detection uses an in-memory bounded cache (max 10,000 entries)
with FIFO eviction.
The cache is cleared on container restart, so restarts do not cause replay
protection across sessions — that trade-off is intentional for simplicity.
"""

import os
import logging
import pika
import xmlrpc.client  # nosec
import defusedxml.xmlrpc
import defusedxml.ElementTree as ET
from collections import OrderedDict
from lxml import etree

from config_utils import parse_rabbit_port, require_env
from sender import send_error_to_queue, flush_buffer, now_utc, setup_exchange, EXCHANGE_NAME

defusedxml.xmlrpc.monkey_patch()


logger = logging.getLogger(__name__)


# ── Environment ────────────────────────────────────────────────────────────────
RABBIT_HOST = os.environ.get("RABBIT_HOST")
RABBIT_PORT = parse_rabbit_port()
RABBIT_VHOST = os.environ.get("RABBIT_VHOST", "/")
RABBIT_USER = os.environ.get("RABBIT_USER")
RABBIT_PASS = os.environ.get("RABBIT_PASS")

ODOO_URL = os.environ.get("ODOO_URL")
ODOO_DB = os.environ.get("ODOO_DB")
ODOO_USER = os.environ.get("ODOO_USER")
ODOO_PASS = os.environ.get("ODOO_PASS")

QUEUE_NAME = os.environ.get("RABBIT_INCOMING_QUEUE", "kassa.incoming")
DLX_NAME = os.environ.get("RABBIT_DLX", "kassa.dlx")
DLQ_NAME = os.environ.get("RABBIT_DLQ", "kassa.incoming.dlq")
DLQ_ROUTING_KEY = os.environ.get("RABBIT_DLX_ROUTING_KEY", DLQ_NAME)

# ── XSD schema mapping ─────────────────────────────────────────────────────────
# Paths to XSD files in the container (/app/schemas/)
SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "schemas")

SCHEMA_MAP = {
    "new_registration": os.path.join(SCHEMA_DIR, "schema_new_registration.xsd"),
    "profile_update": os.path.join(SCHEMA_DIR, "schema_profile_update.xsd"),
    "badge_scanned": os.path.join(SCHEMA_DIR, "schema_badge_scanned.xsd"),
    "cancel_registration": os.path.join(SCHEMA_DIR, "schema_cancel_registration.xsd"),
}

# Cache parsed XSD schemas — avoids re-parsing from disk on every message.
# Mirrors the same pattern used in sender.py (_schema_cache).
_schema_cache: dict[str, etree.XMLSchema] = {}

# ── Idempotency cache ──────────────────────────────────────────────────────────
MAX_CACHE_SIZE = 10_000
seen_message_ids: OrderedDict = OrderedDict()


def _remember_message_id(message_id: str) -> None:
    seen_message_ids[message_id] = now_utc()
    if len(seen_message_ids) > MAX_CACHE_SIZE:
        seen_message_ids.popitem(last=False)


def is_duplicate(message_id: str, track_if_new: bool = True) -> bool:
    """
    Return True if this message_id has already been processed in this session.

    Uses an OrderedDict as a bounded FIFO cache. When the cache hits
    MAX_CACHE_SIZE the oldest entry is evicted (popitem(last=False)) to keep
    memory usage constant. The timestamp stored as the value is only for
    debugging — it is not used for expiry.

    track_if_new controls whether new IDs should be added immediately. The
    receiver callback uses track_if_new=False and only remembers IDs after a
    successful full processing + ACK.
    """
    if message_id in seen_message_ids:
        logger.info("[IDEMPOTENCY] Duplicate detected: message_id=%s – skipped", message_id)
        return True
    if track_if_new:
        _remember_message_id(message_id)
    return False


# ── Odoo connection ────────────────────────────────────────────────────────────
def get_odoo_connection():
    """
    Open an XML-RPC session with Odoo and return (uid, models proxy).

    Reads credentials from the environment via require_env so the error
    message names every missing variable at once. Raises ConnectionError if
    authentication succeeds but Odoo returns uid=0/False (wrong password or
    database name).
    """
    required = require_env("ODOO_URL", "ODOO_DB", "ODOO_USER", "ODOO_PASS")
    common = xmlrpc.client.ServerProxy(f"{required['ODOO_URL']}/xmlrpc/2/common")
    uid = common.authenticate(
        required["ODOO_DB"], required["ODOO_USER"], required["ODOO_PASS"], {}
    )
    if not uid:
        raise ConnectionError(
            "Odoo authentication failed. Check ODOO_USER/ODOO_PASS and ODOO_DB."
        )
    models = xmlrpc.client.ServerProxy(f"{required['ODOO_URL']}/xmlrpc/2/object")
    return uid, models


# ── XSD validation ─────────────────────────────────────────────────────────────
def validate_xml(xml_text: str, msg_type: str) -> None:
    """
    Validate xml_text against the XSD schema for msg_type.

    Schema files live in the schemas/ directory next to this file and are
    named schema_<msg_type>.xsd. If no schema exists for a given type the
    validation is skipped and a warning is printed — this lets us deploy new
    message types before their schema is finalised.

    Parsed schemas are cached in _schema_cache after their first use so that
    the XSD file is only read from disk once per process lifetime.

    Raises ValueError with the full lxml error log if validation fails.
    """
    schema_path = SCHEMA_MAP.get(msg_type)
    if not schema_path or not os.path.exists(schema_path):
        logger.warning("[VALIDATION] No XSD schema found for type '%s' – skipping validation", msg_type)
        return

    if msg_type not in _schema_cache:
        schema_doc = etree.parse(schema_path)
        _schema_cache[msg_type] = etree.XMLSchema(schema_doc)

    xml_doc = etree.fromstring(xml_text.encode("utf-8"))

    if not _schema_cache[msg_type].validate(xml_doc):
        errors = str(_schema_cache[msg_type].error_log)
        raise ValueError(f"XSD validation failed for '{msg_type}':\n{errors}")

    logger.info("[VALIDATION] ✓ XSD validation passed for type '%s'", msg_type)


# ── Business logic per message type ───────────────────────────────────────────

def process_new_registration(root: ET.Element, uid: int, models) -> None:
    """
    Handle a new_registration message (Flow 1).

    Looks up the customer by x_user_id in res.partner. If found, updates the
    existing record; if not, creates a new one. This makes the handler
    idempotent at the Odoo level as well — reprocessing the same message after
    a container restart does not create a duplicate partner.

    The <payment_due> block is logged for audit purposes but not stored as a
    separate Odoo record in this version.
    """
    body = root.find("body")
    if body is None:
        raise ValueError("new_registration: <body> missing")

    customer = body.find("customer")
    if customer is None:
        raise ValueError("new_registration: <customer> missing in <body>")

    user_id = customer.findtext("user_id", "").strip()
    email = customer.findtext("email", "").strip()

    contact = customer.find("contact")
    first_name = contact.findtext("first_name", "").strip() if contact is not None else ""
    last_name = contact.findtext("last_name", "").strip() if contact is not None else ""
    contact_name = " ".join(part for part in [first_name, last_name] if part).strip()
    name = customer.findtext("name", "").strip() or contact_name

    company_name = customer.findtext("company_name", "").strip()
    ctype = customer.findtext("type", "private").strip().lower()
    vat_number = customer.findtext("vat_number", "").strip()

    dob_str = customer.findtext("date_of_birth", "").strip()

    payment_due_el = body.find("payment_due")
    if payment_due_el is None:
        raise ValueError("new_registration: <payment_due> missing in <body>")

    # amount is validated by XSD and no longer logged (PII)
    status = payment_due_el.findtext("status", "unpaid").strip()

    if not user_id:
        raise ValueError("new_registration: user_id missing in <customer>")

    existing = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "res.partner", "search_read",
        [[["x_user_id", "=", user_id]]],
        {"fields": ["id", "name", "x_user_id"], "limit": 1},
    )

    partner_vals = {
        "name": name or company_name or "Unknown",
        "email": email,
        "x_user_id": user_id,
        "is_company": ctype == "company",
    }
    if dob_str:
        partner_vals["x_date_of_birth"] = dob_str
    if vat_number:
        partner_vals["vat"] = vat_number

    if existing:
        partner_id = existing[0]["id"]
        models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "res.partner", "write",
            [[partner_id], partner_vals],
        )
        logger.info("[NEW_REGISTRATION] ✓ Customer updated: Odoo ID=%s", partner_id)
    else:
        partner_id = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "res.partner", "create",
            [partner_vals],
        )
        logger.info("[NEW_REGISTRATION] ✓ New customer created: Odoo ID=%s", partner_id)

    logger.info("[NEW_REGISTRATION]   Payment due status: %s", status)


def process_profile_update(root: ET.Element, uid: int, models) -> None:
    """
    Handle a profile_update message (Flow 3).

    Finds the partner by x_user_id and writes the new values. If the partner
    does not exist yet (e.g. a profile update arrived before the registration
    message), it creates a new partner as a fallback rather than dropping the
    update silently.
    """
    body = root.find("body")
    if body is None:
        raise ValueError("profile_update: <body> missing")

    user_id = body.findtext("user_id", "").strip()
    email = body.findtext("email", "").strip()

    contact = body.find("contact")
    first_name = contact.findtext("first_name", "").strip() if contact is not None else ""
    last_name = contact.findtext("last_name", "").strip() if contact is not None else ""
    contact_name = " ".join(part for part in [first_name, last_name] if part).strip()
    name = body.findtext("name", "").strip() or contact_name

    company_name = body.findtext("company_name", "").strip()
    ctype = body.findtext("type", "private").strip().lower()
    vat_number = body.findtext("vat_number", "").strip()

    dob_str = body.findtext("date_of_birth", "").strip()

    if not user_id:
        raise ValueError("profile_update: user_id missing in <body>")

    existing = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "res.partner", "search_read",
        [[["x_user_id", "=", user_id]]],
        {"fields": ["id", "name"], "limit": 1},
    )

    update_vals = {
        "email": email,
        "is_company": ctype == "company",
        "name": name or company_name or "Unknown",
    }
    if body.find("vat_number") is not None:
        update_vals["vat"] = vat_number if vat_number else False
    if body.find("date_of_birth") is not None:
        update_vals["x_date_of_birth"] = dob_str if dob_str else False

    if existing:
        partner_id = existing[0]["id"]
        models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "res.partner", "write",
            [[partner_id], update_vals],
        )
        logger.info("[PROFILE_UPDATE] ✓ Profile updated: Odoo ID=%s", partner_id)
    else:
        update_vals["x_user_id"] = user_id
        partner_id = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "res.partner", "create",
            [update_vals],
        )
        logger.warning("[PROFILE_UPDATE] ⚠ Customer not found – created new: Odoo ID=%s", partner_id)


def process_badge_scan(root: ET.Element, uid: int, models) -> None:
    """
    Handle a badge_scanned message (Flow 2).

    Searches res.partner by x_badge_id. On a hit, logs the customer name and
    wallet balance so the cashier UI can display them. On a miss, sends a
    system_error with code 'badge_not_found' to kassa.errors — the cashier
    then either proceeds as an anonymous sale (Flow 11) or directs the visitor
    to the registration desk.

    Either way the message is ACKed: an unknown badge stays unknown and there
    is nothing to retry.
    """
    body = root.find("body")
    if body is None:
        raise ValueError("badge_scanned: <body> missing")

    badge_id = body.findtext("badge_id", "").strip()
    location = body.findtext("location", "unknown").strip()

    if not badge_id:
        raise ValueError("badge_scanned: badge_id missing in <body>")

    existing = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "res.partner", "search_read",
        [[["x_badge_id", "=", badge_id]]],
        {"fields": ["id", "name", "x_user_id", "x_wallet_balance", "x_date_of_birth", "is_company"], "limit": 1},
    )

    message_id = root.findtext("header/message_id")

    if existing:
        partner = existing[0]
        logger.info(
            "[BADGE_SCANNED] ✓ Badge recognised: Odoo ID=%s | Location=%s",
            partner['id'],
            location,
        )
    else:
        logger.warning("[BADGE_SCANNED] ⚠ Badge NOT found in local cache – sending system_error")
        send_error_to_queue(
            error_code="badge_not_found",
            related_message_id=message_id,
            error_description=f"Badge {badge_id} not found in local Odoo cache.",
        )
        # ACK (not NACK) – an unknown badge stays unknown until Flow 12 runs


def process_cancel_registration(root: ET.Element, uid: int, models) -> None:
    """
    Handle a cancel_registration message (Flow 4).

    Sets active=False on the partner record (Odoo soft-delete). The record is
    kept in the database so historical POS orders and audit trails are not
    broken. If the user_id is not found the message is still ACKed — there is
    nothing to cancel.
    """
    body = root.find("body")
    if body is None:
        raise ValueError("cancel_registration: <body> missing")

    user_id = body.findtext("user_id", "").strip()
    session_id = body.findtext("session_id", "").strip()

    if not user_id:
        raise ValueError("cancel_registration: user_id missing in <body>")

    existing = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "res.partner", "search_read",
        [[["x_user_id", "=", user_id]]],
        {"fields": ["id", "name"], "limit": 1},
    )

    if existing:
        partner_id = existing[0]["id"]
        models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "res.partner", "write",
            [[partner_id], {"active": False}],
        )
        logger.info(
            "[CANCEL_REGISTRATION] ✓ Profile deactivated: Odoo ID=%s | session_id=%s",
            partner_id,
            session_id,
        )
    else:
        logger.warning("[CANCEL_REGISTRATION] ⚠ Customer not found – no action")


# ── Central message processing ─────────────────────────────────────────────────
def process_message(ch, method, properties, body):
    """
    RabbitMQ delivery callback — called once per message by pika.

    Processing pipeline:
      1. Parse XML             — reject immediately if not valid XML
      2. Read header           — extract message_id and type
      3. Idempotency check     — skip if message_id seen before in this session
      4. XSD validation        — reject if message does not match its schema
      5. Odoo connection       — authenticate fresh per message (stateless)
      6. Business logic        — dispatch to the correct process_* function
      7. ACK + remember ID     — cache message_id only after successful handling

    On any validation or business-logic error:
      - A system_error is forwarded to kassa.errors via send_error_to_queue.
      - Validation and business errors use basic_nack(requeue=False).
      - Odoo connection/auth errors use basic_nack(requeue=True).
    """
    xml_text = body.decode("utf-8")
    related_message_id = None

    try:
        # ── Step 1: Parse XML ──────────────────────────────────────────────
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.error("[RECEIVER] ❌ XML parse error: %s", e)
            send_error_to_queue("invalid_xml_format", None, f"XML could not be parsed: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        # ── Step 2: Read header ────────────────────────────────────────────
        header = root.find("header")
        related_message_id = header.findtext("message_id") if header is not None else None
        msg_type = header.findtext("type") if header is not None else None

        if not msg_type:
            send_error_to_queue(
                "invalid_xml_format",
                related_message_id,
                "Message type missing in <header><type>",
            )
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        # ── Step 3: Idempotency check ──────────────────────────────────────
        if related_message_id and is_duplicate(related_message_id, track_if_new=False):
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        logger.info("[RECEIVER] Received: type=%s | message_id=%s", msg_type, related_message_id)

        # ── Step 4: XSD validation ─────────────────────────────────────────
        try:
            validate_xml(xml_text, msg_type)
        except ValueError as e:
            logger.error("[RECEIVER] ❌ XSD validation failed for '%s'", msg_type)
            send_error_to_queue("invalid_xml_format", related_message_id, str(e))
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        # ── Step 5: Odoo connection ────────────────────────────────────────
        uid, models = get_odoo_connection()

        # ── Step 6: Business logic ─────────────────────────────────────────
        if msg_type == "new_registration":
            process_new_registration(root, uid, models)

        elif msg_type == "profile_update":
            process_profile_update(root, uid, models)

        elif msg_type == "badge_scanned":
            process_badge_scan(root, uid, models)

        elif msg_type == "cancel_registration":
            process_cancel_registration(root, uid, models)

        else:
            raise ValueError(f"Unknown message type: '{msg_type}'")

        if related_message_id:
            _remember_message_id(related_message_id)
            logger.info("[IDEMPOTENCY] Stored message_id=%s after successful processing", related_message_id)

        # ── Step 7: ACK on success ─────────────────────────────────────────
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except ValueError as e:
        code = "unknown_message_type" if "Unknown message type" in str(e) else "invalid_xml_format"
        logger.error("[RECEIVER] ❌ %s for message_id=%s: %s", code, related_message_id, e)
        send_error_to_queue(code, related_message_id, str(e))
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    except ConnectionError as e:
        logger.error("[RECEIVER] ❌ Odoo connection error for message_id=%s: %s", related_message_id, e)
        send_error_to_queue("odoo_api_error", related_message_id, str(e))
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    except Exception as e:
        logger.error(
            "[RECEIVER] ❌ Unexpected error for message_id=%s: %s: %s",
            related_message_id, type(e).__name__, e,
        )
        send_error_to_queue("odoo_api_error", related_message_id, str(e))
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


# ── RabbitMQ connection and startup ───────────────────────────────────────────

def connect_to_rabbitmq():
    """
    Open a new blocking connection to RabbitMQ using environment credentials.

    Called once at startup inside start_listening(). If the connection drops,
    the exception propagates up to _run_receiver() in main.py which logs the
    error and retries after 5 seconds.
    """
    credentials = pika.PlainCredentials(RABBIT_USER, RABBIT_PASS)
    params = pika.ConnectionParameters(
        host=RABBIT_HOST,
        port=RABBIT_PORT,
        virtual_host=RABBIT_VHOST,
        credentials=credentials,
    )
    return pika.BlockingConnection(params)


def start_listening():
    """
    Connect to RabbitMQ, flush the outbound buffer, and start consuming.

    prefetch_count=1 means the broker only delivers one unacknowledged message
    at a time. This prevents the receiver from pulling a large batch and then
    crashing mid-way, which would leave many messages unacknowledged.

    flush_buffer() re-sends any consumption_order messages that were buffered
    to outbox.json while the broker was unreachable. Doing it here (on connect)
    rather than in a separate thread keeps the sequencing simple.

    This function blocks inside channel.start_consuming() until the connection
    is lost or an exception is raised. The caller (_run_receiver in main.py)
    is responsible for restarting it.
    """
    conn = connect_to_rabbitmq()
    channel = conn.channel()

    # --- RabbitMQ Setup ---
    try:
        # 0. Ensure the main exchange exists and has the correct type (topic)
        # The sender owns the declaration, so we reuse its setup logic.
        setup_exchange(channel)

        # 1. Declare the Dead Letter Exchange (DLX)
        channel.exchange_declare(exchange=DLX_NAME, exchange_type="direct", durable=True)

        # 2. Declare the Dead Letter Queue (DLQ)
        channel.queue_declare(queue=DLQ_NAME, durable=True)

        # 3. Bind the DLQ to the DLX with an explicit routing key
        channel.queue_bind(exchange=DLX_NAME, queue=DLQ_NAME, routing_key=DLQ_ROUTING_KEY)

        # 4. Declare the main queue with DLX + DLQ routing key settings
        channel.queue_declare(
            queue=QUEUE_NAME,
            durable=True,
            arguments={
                "x-dead-letter-exchange": DLX_NAME,
                "x-dead-letter-routing-key": DLQ_ROUTING_KEY,
            }
        )

        # 5. Bind the main queue to the topic exchange.
        # This ensures messages published to EXCHANGE_NAME with QUEUE_NAME as routing key reach us.
        channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key=QUEUE_NAME)

    except pika.exceptions.ChannelClosedByBroker as exc:
        if getattr(exc, "reply_code", None) == 406:
            logger.critical(
                "RabbitMQ topology conflict (406 PRECONDITION_FAILED). "
                "A queue/exchange already exists with different arguments. "
                "Delete and recreate conflicting resources in RabbitMQ management. "
                "queue=%s, dlx=%s, dlq=%s, broker=%s",
                QUEUE_NAME,
                DLX_NAME,
                DLQ_NAME,
                getattr(exc, "reply_text", "unknown"),
            )
        raise

    channel.basic_qos(prefetch_count=1)

    # Re-publish buffered outbox messages after successful (re)connect.
    # flush_buffer() returns the Odoo order IDs of successfully flushed messages;
    # mark those orders as sent so the poller does not re-process them.
    flushed_ids = flush_buffer()
    if flushed_ids:
        try:
            uid, models = get_odoo_connection()
            unique_ids = list(set(flushed_ids))
            models.execute_kw(
                ODOO_DB, uid, ODOO_PASS,
                'pos.order', 'write',
                [unique_ids, {'x_rabbitmq_sent': True}]
            )
            logger.info("[RECEIVER] ✓ Marked %d buffered orders as sent after flush", len(unique_ids))
        except Exception as e:
            logger.warning("[RECEIVER] ⚠️  Could not mark flushed orders as sent: %s", e)

    channel.basic_consume(
        queue=QUEUE_NAME,
        on_message_callback=process_message,
    )

    logger.info("[RECEIVER] ✓ Listening on queue: %s", QUEUE_NAME)
    logger.info("[RECEIVER]   Odoo: %s | DB: %s", ODOO_URL, ODOO_DB)
    logger.info("[RECEIVER]   Waiting for messages…")

    channel.start_consuming()


if __name__ == "__main__":
    start_listening()
