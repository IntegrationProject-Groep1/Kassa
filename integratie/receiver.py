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
    - Odoo connection/API error → retry up to 3 times via RETRY_QUEUE, then DLQ
    - Duplicate message_id     → basic_ack, no Odoo write (silently ignored)

Duplicate detection uses an in-memory bounded cache (max 10,000 entries)
with FIFO eviction.
"""

import os
import logging
import pika
import xmlrpc.client  # nosec
import defusedxml.xmlrpc
import defusedxml.ElementTree as ET
from xml.etree.ElementTree import Element
from collections import OrderedDict
from typing import Any, List, Dict, Tuple, cast
from lxml import etree

from config_utils import get_env, parse_rabbit_port, require_env, parse_xml_float
from sender import send_error_to_queue, flush_buffer, now_utc, setup_exchange, EXCHANGE_NAME
from monitoring import monitor
from typing_utils import OdooModelsProxy, OdooRecord

defusedxml.xmlrpc.monkey_patch()


logger = logging.getLogger(__name__)


# ── Environment ────────────────────────────────────────────────────────────────
_rabbit_env = require_env("RABBIT_HOST", "RABBIT_USER", "RABBIT_PASS")
RABBIT_HOST = _rabbit_env["RABBIT_HOST"]
RABBIT_USER = _rabbit_env["RABBIT_USER"]
RABBIT_PASS = _rabbit_env["RABBIT_PASS"]

RABBIT_PORT = parse_rabbit_port()
RABBIT_VHOST = os.environ.get("RABBIT_VHOST", "/")

_odoo_env = require_env("ODOO_URL", "ODOO_DB", "ODOO_USER", "ODOO_PASS")
ODOO_URL = _odoo_env["ODOO_URL"]
ODOO_DB = _odoo_env["ODOO_DB"]
ODOO_USER = _odoo_env["ODOO_USER"]
ODOO_PASS = _odoo_env["ODOO_PASS"]

QUEUE_NAME = get_env("RABBIT_INCOMING_QUEUE", "kassa.incoming")
DLX_NAME = get_env("RABBIT_DLX", EXCHANGE_NAME)
DLQ_NAME = get_env("RABBIT_DLQ", "kassa.incoming.dlq")
DLQ_ROUTING_KEY = get_env("RABBIT_DLX_ROUTING_KEY", DLQ_NAME)

RETRY_QUEUE = f"{QUEUE_NAME}.retry"
RETRY_DELAY_MS = 5000  # 5 seconds
MAX_RETRIES = 3

# Performance optimization: Toggle success-level monitoring logs (high frequency)
# This prevents bloating the monitoring queue during high-traffic events.
_monitor_logs_env = get_env("MONITOR_SUCCESS_LOGS", "True") or "True"
MONITOR_SUCCESS_LOGS = _monitor_logs_env.lower() == "true"

# ── XSD schema mapping ─────────────────────────────────────────────────────────
SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "schemas")

SCHEMA_MAP = {
    "new_registration": os.path.join(SCHEMA_DIR, "schema_new_registration.xsd"),
    "profile_update": os.path.join(SCHEMA_DIR, "schema_profile_update.xsd"),
    "badge_scanned": os.path.join(SCHEMA_DIR, "schema_badge_scanned.xsd"),
    "cancel_registration": os.path.join(SCHEMA_DIR, "schema_cancel_registration.xsd"),
}

_schema_cache: dict[str, etree.XMLSchema] = {}


def _normalize_for_validation(xml_text: str, msg_type: str) -> str:
    """
    Contract v2.3 alignment: No normalization required as CRM and Kassa
    now follow the same centralized schema definitions.
    """
    return xml_text


# ── Idempotency cache ──────────────────────────────────────────────────────────
MAX_CACHE_SIZE = 10_000
seen_message_ids: OrderedDict = OrderedDict()


def _remember_message_id(message_id: str) -> None:
    seen_message_ids[message_id] = now_utc()
    if len(seen_message_ids) > MAX_CACHE_SIZE:
        seen_message_ids.popitem(last=False)


def is_duplicate(message_id: str, track_if_new: bool = True) -> bool:
    """Return True if this message_id has already been processed in this session."""
    if message_id in seen_message_ids:
        logger.info("[IDEMPOTENCY] Duplicate detected: message_id=%s – skipped", message_id)
        return True
    if track_if_new:
        _remember_message_id(message_id)
    return False


# ── Odoo connection ────────────────────────────────────────────────────────────
def get_odoo_connection() -> Tuple[int, OdooModelsProxy]:
    """Open an XML-RPC session with Odoo and return (uid, models proxy)."""
    required = require_env("ODOO_URL", "ODOO_DB", "ODOO_USER", "ODOO_PASS")
    common = xmlrpc.client.ServerProxy(f"{required['ODOO_URL']}/xmlrpc/2/common")
    uid = common.authenticate(
        required["ODOO_DB"], required["ODOO_USER"], required["ODOO_PASS"], {}
    )
    if not isinstance(uid, int) or uid <= 0:
        raise ConnectionError(
            "Odoo authentication failed. Check ODOO_USER/ODOO_PASS and ODOO_DB."
        )
    models = xmlrpc.client.ServerProxy(f"{required['ODOO_URL']}/xmlrpc/2/object")
    return uid, cast(OdooModelsProxy, models)


# ── XSD validation ─────────────────────────────────────────────────────────────
def validate_xml(xml_text: str, msg_type: str) -> None:
    """Validate xml_text against the XSD schema for msg_type."""
    schema_path = SCHEMA_MAP.get(msg_type)
    if not schema_path or not os.path.exists(schema_path):
        logger.warning("[VALIDATION] No XSD schema found for type '%s' – skipping validation", msg_type)
        return

    if msg_type not in _schema_cache:
        schema_doc = etree.parse(schema_path)
        _schema_cache[msg_type] = etree.XMLSchema(schema_doc)

    validation_xml = _normalize_for_validation(xml_text, msg_type)
    xml_doc = etree.fromstring(validation_xml.encode("utf-8"))

    if not _schema_cache[msg_type].validate(xml_doc):
        errors = str(_schema_cache[msg_type].error_log)
        raise ValueError(f"XSD validation failed for '{msg_type}':\n{errors}")

    logger.info("[VALIDATION] ✓ XSD validation passed for type '%s'", msg_type)


# ── Bus event publisher ────────────────────────────────────────────────────────

def _publish_partner_bus_event(
    uid: int, models, partner_id: int,
    outstanding_amount: float, payment_status: str, name: str,
) -> None:
    """
    Publish a kassa_partner_update bus event via the PosOrder XML-RPC wrapper.

    In Odoo 17 the bus.bus._sendone method is private and cannot be called
    directly from an external XML-RPC session.  The public wrapper
    pos.order.send_partner_bus_event is defined in kassa_pos_custom and
    provides the bridge.  A failure here is non-fatal — the partner data is
    already written to Odoo, only the real-time POS update is delayed.
    """
    try:
        models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "pos.order", "send_partner_bus_event",
            [partner_id, outstanding_amount, payment_status, name],
        )
        logger.info("[BUS] ✓ Published partner update: partner_id=%s", partner_id)
    except Exception as e:
        logger.warning("[BUS] Could not publish bus event for partner_id=%s: %s", partner_id, e)


# ── Business logic per message type ───────────────────────────────────────────

def process_new_registration(root: Element, uid: int, models: OdooModelsProxy) -> None:
    """Handle a new_registration message (Flow 1)."""
    body = root.find("body")
    if body is None:
        raise ValueError("new_registration: <body> missing")

    customer = body.find("customer")
    if customer is None:
        raise ValueError("new_registration: <customer> missing in <body>")

    identity_uuid = (customer.findtext("identity_uuid") or "").strip()
    email = (customer.findtext("email") or "").strip()

    contact = customer.find("contact")
    first_name = (contact.findtext("first_name") or "").strip() if contact is not None else ""
    last_name = (contact.findtext("last_name") or "").strip() if contact is not None else ""
    contact_name = " ".join(part for part in [first_name, last_name] if part).strip()

    # Fallback for old 'name' tag if present, but priority to first+last name
    name = contact_name or (customer.findtext("name") or "").strip()

    company_name = (customer.findtext("company_name") or "").strip()
    ctype = (customer.findtext("type") or "private").strip().lower()
    vat_number = (customer.findtext("vat_number") or "").strip()
    dob_str = (customer.findtext("date_of_birth") or "").strip()
    company_id = (customer.findtext("company_id") or "").strip()
    badge_id = (customer.findtext("badge_id") or "").strip()
    session_id = (customer.findtext("session_id") or "").strip()
    session_title = (customer.findtext("session_title") or "").strip()

    payment_due_el = customer.find("payment_due")
    if payment_due_el is None:
        # Compatibility fallback if payment_due was moved to body by normalization
        payment_due_el = body.find("payment_due")

    if payment_due_el is None:
        raise ValueError("new_registration: <payment_due> missing in <customer>")

    status = (payment_due_el.findtext("status") or "unpaid").strip()
    amount = parse_xml_float(payment_due_el.find("amount"))

    if not identity_uuid:
        raise ValueError("new_registration: identity_uuid missing in <customer>")

    # Contract Section 11.1: VAT number required for companies
    if ctype == "company" and not vat_number:
        raise ValueError(
            "new_registration: vat_number is mandatory for company type per contract Section 11.1"
        )

    existing: List[OdooRecord] = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "res.partner", "search_read",
        [[["x_user_id", "=", identity_uuid]]],
        {"fields": ["id", "name", "x_user_id"], "limit": 1},
    )

    partner_vals: Dict[str, Any] = {
        "name": name or company_name or "Unknown",
        "email": email,
        "x_user_id": identity_uuid,
        "is_company": ctype == "company",
        "x_session_id": session_id,
        "x_payment_status": status,
        "x_outstanding_amount": amount,
    }
    if session_title:
        partner_vals["x_session_title"] = session_title
    if badge_id:
        partner_vals["x_badge_id"] = badge_id
    if company_id:
        partner_vals["x_company_id"] = company_id
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
    _publish_partner_bus_event(
        uid, models, partner_id,
        amount, status, partner_vals["name"],
    )


def process_profile_update(root: Element, uid: int, models: OdooModelsProxy) -> None:
    """Handle a profile_update message (Flow 3)."""
    body = root.find("body")
    if body is None:
        raise ValueError("profile_update: <body> missing")

    identity_uuid = (body.findtext("identity_uuid") or "").strip()
    email = (body.findtext("email") or "").strip()

    contact = body.find("contact")
    first_name = (contact.findtext("first_name") or "").strip() if contact is not None else ""
    last_name = (contact.findtext("last_name") or "").strip() if contact is not None else ""
    contact_name = " ".join(part for part in [first_name, last_name] if part).strip()

    # Fallback for old 'name' tag if present
    name = contact_name or (body.findtext("name") or "").strip()

    company_name = (body.findtext("company_name") or "").strip()
    ctype = (body.findtext("type") or "private").strip().lower()
    vat_number = (body.findtext("vat_number") or "").strip()
    dob_str = (body.findtext("date_of_birth") or "").strip()
    company_id = (body.findtext("company_id") or "").strip()

    payment_due_el = body.find("payment_due")

    if not identity_uuid:
        raise ValueError("profile_update: identity_uuid missing in <body>")

    existing: List[OdooRecord] = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "res.partner", "search_read",
        [[["x_user_id", "=", identity_uuid]]],
        {"fields": ["id", "name"], "limit": 1},
    )

    update_vals: Dict[str, Any] = {
        "email": email,
        "is_company": ctype == "company",
        "name": name or company_name or "Unknown",
    }
    if company_id:
        update_vals["x_company_id"] = company_id
    if payment_due_el is not None:
        status = (payment_due_el.findtext("status") or "pending").strip()
        amount = parse_xml_float(payment_due_el.find("amount"))
        update_vals["x_payment_status"] = status
        update_vals["x_outstanding_amount"] = amount
    if body.find("vat_number") is not None:
        update_vals["vat"] = vat_number if vat_number else False
    if company_name and not name:
        update_vals["name"] = company_name
    if body.find("date_of_birth") is not None:
        update_vals["x_date_of_birth"] = dob_str if dob_str else False

    payment_due_el = body.find("payment_due")
    if payment_due_el is not None:
        try:
            outstanding_amount = float(payment_due_el.findtext("amount", "0").strip())
        except ValueError:
            outstanding_amount = 0.0
        payment_status = payment_due_el.findtext("status", "unpaid").strip()
        update_vals["x_outstanding_amount"] = outstanding_amount
        update_vals["x_payment_status"] = payment_status
    else:
        outstanding_amount = None
        payment_status = None

    if existing:
        partner_id = existing[0]["id"]
        models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "res.partner", "write",
            [[partner_id], update_vals],
        )
        logger.info("[PROFILE_UPDATE] ✓ Profile updated: Odoo ID=%s", partner_id)
    else:
        update_vals["x_user_id"] = identity_uuid
        partner_id = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "res.partner", "create",
            [update_vals],
        )
        logger.warning("[PROFILE_UPDATE] ⚠ Customer not found – created new: Odoo ID=%s", partner_id)

    if outstanding_amount is not None and payment_status is not None:
        _publish_partner_bus_event(
            uid, models, partner_id,
            outstanding_amount, payment_status, update_vals.get("name", "Unknown"),
        )


def process_badge_scan(root: Element, uid: int, models: OdooModelsProxy) -> None:
    """Handle a badge_scanned message (Flow 2)."""
    body = root.find("body")
    if body is None:
        raise ValueError("badge_scanned: <body> missing")

    badge_id = (body.findtext("badge_id") or "").strip()
    scan_type = (body.findtext("scan_type") or "").strip()
    location = (body.findtext("location") or scan_type or "unknown").strip()
    scanned_at = (body.findtext("scanned_at") or "").strip()

    if not badge_id:
        raise ValueError("badge_scanned: badge_id missing in <body>")

    logger.info("[BADGE_SCANNED] Processing scan from %s at %s", location, scanned_at)

    existing: List[OdooRecord] = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "res.partner", "search_read",
        [[["x_badge_id", "=", badge_id]]],
        {"fields": ["id", "name", "x_user_id", "x_wallet_balance",
                    "x_date_of_birth", "is_company"], "limit": 1},
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


def process_cancel_registration(root: Element, uid: int, models: OdooModelsProxy) -> None:
    """Handle a cancel_registration message (Flow 4)."""
    body = root.find("body")
    if body is None:
        raise ValueError("cancel_registration: <body> missing")

    identity_uuid = (body.findtext("identity_uuid") or "").strip()
    session_id = (body.findtext("session_id") or "").strip()
    reason = (body.findtext("reason") or "").strip()

    if not identity_uuid:
        raise ValueError("cancel_registration: identity_uuid missing in <body>")

    existing: List[OdooRecord] = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "res.partner", "search_read",
        [[["x_user_id", "=", identity_uuid]]],
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
            "[CANCEL_REGISTRATION] ✓ Profile deactivated: Odoo ID=%s | session_id=%s | reason=%s",
            partner_id,
            session_id,
            reason,
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
      - Odoo connection/auth errors are retried up to MAX_RETRIES.
    """
    xml_text = body.decode("utf-8")
    related_message_id = None

    try:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.error("[RECEIVER] ❌ XML parse error: %s", e)
            monitor.log("error", "xml_validation", f"Unparseable XML received: {str(e)[:500]}")
            send_error_to_queue("invalid_xml_format", None, f"XML could not be parsed: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        header = root.find("header")
        related_message_id = header.findtext("message_id") if header is not None else None
        msg_type = header.findtext("type") if header is not None else None

        if not msg_type:
            send_error_to_queue("invalid_xml_format", related_message_id, "Message type missing")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        if related_message_id and is_duplicate(related_message_id, track_if_new=False):
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        logger.info("[RECEIVER] Received: type=%s | message_id=%s", msg_type, related_message_id)

        try:
            validate_xml(xml_text, msg_type)
        except ValueError as e:
            logger.error("[RECEIVER] ❌ Validation failure for '%s': %s", msg_type, e)
            monitor.log(
                "error", "xml_validation",
                f"Validation failure for {msg_type} (ID: {related_message_id or 'unknown'}): {str(e)[:500]}"
            )
            send_error_to_queue("invalid_xml_format", related_message_id, str(e))
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        if msg_type not in SCHEMA_MAP:
            raise ValueError(f"Unknown message type: '{msg_type}'")

        uid, models = get_odoo_connection()

        if msg_type == "new_registration":
            process_new_registration(root, uid, models)
        elif msg_type == "profile_update":
            process_profile_update(root, uid, models)
        elif msg_type == "badge_scanned":
            process_badge_scan(root, uid, models)
        elif msg_type == "cancel_registration":
            process_cancel_registration(root, uid, models)

        if related_message_id:
            _remember_message_id(related_message_id)
        ch.basic_ack(delivery_tag=method.delivery_tag)

        # Successful processing is logged locally always,
        # but monitoring is optional to prevent queue bloat.
        if MONITOR_SUCCESS_LOGS:
            monitor.log(
                "info", "xml_validation",
                f"Successfully processed {msg_type} (ID: {related_message_id or 'unknown'})"
            )

    except ValueError as e:
        error_str = str(e)
        if "Unknown message type" in error_str:
            code = "unknown_message_type"
        else:
            code = "invalid_xml_format"
        logger.error("[RECEIVER] ❌ %s: %s", code, e)
        send_error_to_queue(code, related_message_id, error_str)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    except ConnectionError as e:
        retries = properties.headers.get("x-retry-count", 0) if properties and properties.headers else 0
        if retries < MAX_RETRIES:
            logger.warning("[RECEIVER] ⚠ Odoo error (retry %d/%d): %s", retries + 1, MAX_RETRIES, e)
            new_headers = properties.headers.copy() if properties and properties.headers else {}
            new_headers["x-retry-count"] = retries + 1
            ch.basic_publish(
                exchange="", routing_key=RETRY_QUEUE, body=body,
                properties=pika.BasicProperties(headers=new_headers, delivery_mode=2)
            )
            ch.basic_ack(delivery_tag=method.delivery_tag)
        else:
            logger.error("[RECEIVER] ❌ Max retries reached: %s", e)
            monitor.log(
                "error", "system_error",
                f"Receiver: Max retries reached for message {related_message_id}: {str(e)[:500]}"
            )
            send_error_to_queue("odoo_api_error", related_message_id, f"Max retries reached: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    except Exception as e:
        logger.error("[RECEIVER] ❌ Unexpected error: %s", e)
        monitor.log(
            "error", "system_error",
            f"Unexpected receiver error for {related_message_id or 'unknown'}: {str(e)[:500]}"
        )
        send_error_to_queue("odoo_api_error", related_message_id, str(e))
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


# ── RabbitMQ connection and startup ───────────────────────────────────────────

def connect_to_rabbitmq():
    """Open a new blocking connection to RabbitMQ using environment credentials."""
    required = require_env("RABBIT_HOST", "RABBIT_USER", "RABBIT_PASS")
    credentials = pika.PlainCredentials(required["RABBIT_USER"], required["RABBIT_PASS"])
    params = pika.ConnectionParameters(
        host=required["RABBIT_HOST"], port=RABBIT_PORT, virtual_host=RABBIT_VHOST, credentials=credentials,
    )
    return pika.BlockingConnection(params)


def start_listening():
    """Connect to RabbitMQ and start consuming."""
    conn = connect_to_rabbitmq()
    channel = conn.channel()

    try:
        setup_exchange(channel)
        dead_letter_exchange = DLX_NAME
        if DLX_NAME != EXCHANGE_NAME:
            channel.exchange_declare(exchange=DLX_NAME, exchange_type="direct", durable=True)
        channel.queue_declare(queue=DLQ_NAME, durable=True)
        channel.queue_bind(exchange=dead_letter_exchange, queue=DLQ_NAME, routing_key=DLQ_ROUTING_KEY)

        channel.queue_declare(
            queue=QUEUE_NAME, durable=True,
            arguments={"x-dead-letter-exchange": dead_letter_exchange,
                       "x-dead-letter-routing-key": DLQ_ROUTING_KEY}
        )

        channel.queue_declare(
            queue=RETRY_QUEUE, durable=True,
            arguments={
                "x-message-ttl": RETRY_DELAY_MS,
                "x-dead-letter-exchange": EXCHANGE_NAME,
                "x-dead-letter-routing-key": f"{QUEUE_NAME}.retry-recovery",
            }
        )
        channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME,
                           routing_key=f"{QUEUE_NAME}.retry-recovery")
        channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key=f"{QUEUE_NAME}.#")

    except pika.exceptions.ChannelClosedByBroker as exc:
        if getattr(exc, "reply_code", None) == 406:
            logger.critical(
                "RabbitMQ topology conflict (406 PRECONDITION_FAILED) while declaring "
                "exchange=%s queue=%s dlq=%s retry_queue=%s: %s",
                EXCHANGE_NAME,
                QUEUE_NAME,
                DLQ_NAME,
                RETRY_QUEUE,
                getattr(exc, "reply_text", ""),
            )
        raise
    except Exception:
        logger.critical("Failed to setup RabbitMQ topology")
        raise

    channel.basic_qos(prefetch_count=1)
    # Optional: flush buffer on start
    try:
        flushed_ids = flush_buffer()
        if flushed_ids:
            uid, models = get_odoo_connection()
            models.execute_kw(
                ODOO_DB, uid, ODOO_PASS, 'pos.order', 'write',
                [list(set(flushed_ids)), {'x_rabbitmq_sent': True}]
            )
    except Exception as e:
        logger.warning("Could not flush on startup: %s", e)
        monitor.log("warning", "system_error", f"Startup flush failure: {str(e)[:500]}")

    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_message)
    logger.info("[RECEIVER] ✓ Listening on queue: %s", QUEUE_NAME)
    channel.start_consuming()


if __name__ == "__main__":
    start_listening()
