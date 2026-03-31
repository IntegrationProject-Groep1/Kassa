# receiver.py – v3.3
# Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026
#
# Listens on queue.incoming and processes:
#   - new_registration     → create/update customer in Odoo
#   - profile_update       → update customer profile in Odoo
#   - badge_scanned        → look up customer via x_badge_id
#   - cancel_registration  → deactivate customer profile in Odoo
#
# Imports from sender.py (conform Technische Gids v3.3)
# Idempotency via OrderedDict LRU cache (max 10,000 items)

import os
import pika
import xmlrpc.client
import xml.etree.ElementTree as ET
from collections import OrderedDict
from lxml import etree

from config_utils import get_env, parse_rabbit_port, require_env
from sender import send_error_to_queue, flush_buffer, now_utc


# ── Environment ────────────────────────────────────────────────────────────────
RABBIT_HOST = get_env("RABBIT_HOST")
RABBIT_PORT = parse_rabbit_port()
RABBIT_VHOST = get_env("RABBIT_VHOST", "/")
RABBIT_USER = get_env("RABBIT_USER")
RABBIT_PASS = get_env("RABBIT_PASS")

ODOO_URL = os.environ.get("ODOO_URL")
ODOO_DB = os.environ.get("ODOO_DB")
ODOO_USER = os.environ.get("ODOO_USER")
ODOO_PASS = os.environ.get("ODOO_PASS")

QUEUE_NAME = os.environ.get("RABBIT_INCOMING_QUEUE", "kassa.incoming")

# ── XSD schema mapping ─────────────────────────────────────────────────────────
# Paths to XSD files in the container (/app/schemas/)
SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "schemas")

SCHEMA_MAP = {
    "new_registration": os.path.join(SCHEMA_DIR, "schema_nieuwe_inschrijving.xsd"),
    "profile_update": os.path.join(SCHEMA_DIR, "schema_profiel_update.xsd"),
    "badge_scanned": os.path.join(SCHEMA_DIR, "schema_scan_badge.xsd"),
    "cancel_registration": os.path.join(SCHEMA_DIR, "schema_cancel_registration.xsd"),
}

# ── Idempotency cache ──────────────────────────────────────────────────────────
MAX_CACHE_SIZE = 10_000
seen_message_ids: OrderedDict = OrderedDict()


def is_duplicate(message_id: str) -> bool:
    """
    Check whether this message_id was already processed.
    Uses LRU eviction at MAX_CACHE_SIZE.
    """
    if message_id in seen_message_ids:
        print(f"[IDEMPOTENCY] Duplicate detected: {message_id} – skipped")
        return True
    seen_message_ids[message_id] = now_utc()
    if len(seen_message_ids) > MAX_CACHE_SIZE:
        seen_message_ids.popitem(last=False)
    return False


# ── Odoo connection ────────────────────────────────────────────────────────────
def get_odoo_connection():
    """
    Connect to Odoo via XML-RPC.
    Returns (uid, models).
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
    Validate XML against the corresponding XSD schema.
    Raises ValueError when validation fails or schema is not found.
    """
    schema_path = SCHEMA_MAP.get(msg_type)
    if not schema_path or not os.path.exists(schema_path):
        print(f"[VALIDATION] No XSD schema found for type '{msg_type}' – skipping validation")
        return

    schema_doc = etree.parse(schema_path)
    schema = etree.XMLSchema(schema_doc)
    xml_doc = etree.fromstring(xml_text.encode("utf-8"))

    if not schema.validate(xml_doc):
        errors = str(schema.error_log)
        raise ValueError(f"XSD validation failed for '{msg_type}':\n{errors}")

    print(f"[VALIDATION] ✓ XSD validation passed for type '{msg_type}'")


# ── Business logic per message type ───────────────────────────────────────────

def process_new_registration(root: ET.Element, uid: int, models) -> None:
    """
    Flow 1 – new_registration
    Create customer in Odoo, or update if already exists via x_user_id.
    Also stores outstanding registration amount as payment_due.
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
    age_text = customer.findtext("age", "0").strip()
    age = int(age_text) if age_text.isdigit() else 0

    payment_due_el = body.find("payment_due")
    if payment_due_el is None:
        raise ValueError("new_registration: <payment_due> missing in <body>")

    amount = float(payment_due_el.findtext("amount", "0"))
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
        "x_age": age,
    }
    if vat_number:
        partner_vals["vat"] = vat_number

    if existing:
        partner_id = existing[0]["id"]
        models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "res.partner", "write",
            [[partner_id], partner_vals],
        )
        print(f"[NEW_REGISTRATION] ✓ Customer updated: {name} (Odoo ID={partner_id}, user_id={user_id})")
    else:
        partner_id = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "res.partner", "create",
            [partner_vals],
        )
        print(f"[NEW_REGISTRATION] ✓ New customer created: {name} (Odoo ID={partner_id}, user_id={user_id})")

    print(f"[NEW_REGISTRATION]   Outstanding amount: EUR {amount:.2f} | Status: {status}")


def process_profile_update(root: ET.Element, uid: int, models) -> None:
    """
    Flow 3 – profile_update
    Update existing customer profile in Odoo based on x_user_id.
    Defensive: creates customer if not found.
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
    age_text = body.findtext("age", "0").strip()
    age = int(age_text) if age_text.isdigit() else 0

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
        "x_age": age,
    }
    if name:
        update_vals["name"] = name
    if company_name and ctype == "company":
        update_vals["name"] = company_name
    if vat_number:
        update_vals["vat"] = vat_number

    if existing:
        partner_id = existing[0]["id"]
        models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "res.partner", "write",
            [[partner_id], update_vals],
        )
        print(f"[PROFILE_UPDATE] ✓ Profile updated: {name or user_id} (Odoo ID={partner_id})")
    else:
        update_vals["x_user_id"] = user_id
        partner_id = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "res.partner", "create",
            [update_vals],
        )
        print(f"[PROFILE_UPDATE] ⚠ Customer not found – created new (Odoo ID={partner_id}, user_id={user_id})")


def process_badge_scan(root: ET.Element, uid: int, models) -> None:
    """
    Flow 2 – badge_scanned
    Look up customer via x_badge_id in Odoo local cache.
    If not found: send system_error (badge_not_found).
    Cashier then decides: anonymous sale (Flow 11) or redirect to registration desk.
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
        {"fields": ["id", "name", "x_user_id", "x_wallet_balance", "x_age", "is_company"], "limit": 1},
    )

    message_id = root.findtext("header/message_id")

    if existing:
        partner = existing[0]
        print(
            f"[BADGE_SCANNED] ✓ Badge {badge_id} recognised: {partner['name']} | "
            f"Balance: EUR {partner.get('x_wallet_balance', 0):.2f} | "
            f"Location: {location}"
        )
    else:
        print(f"[BADGE_SCANNED] ⚠ Badge {badge_id} NOT found in local cache – sending system_error")
        send_error_to_queue(
            error_code="badge_not_found",
            related_message_id=message_id,
            error_description=f"Badge {badge_id} not found in local Odoo cache.",
        )
        # ACK (not NACK) – an unknown badge stays unknown until Flow 12 runs


def process_cancel_registration(root: ET.Element, uid: int, models) -> None:
    """
    Flow 4 – cancel_registration
    Deactivate customer profile in Odoo based on x_user_id.
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
        print(
            f"[CANCEL_REGISTRATION] ✓ Profile deactivated: {existing[0]['name']} "
            f"(Odoo ID={partner_id}, session_id={session_id})"
        )
    else:
        print(f"[CANCEL_REGISTRATION] ⚠ Customer not found for user_id={user_id} – no action")


# ── Central message processing ─────────────────────────────────────────────────

def process_message(ch, method, properties, body):
    """
    Callback for every incoming RabbitMQ message.
    Step 1: Parse XML
    Step 2: Idempotency check
    Step 3: XSD validation
    Step 4: Business logic per message type
    Step 5: ACK on success, NACK on validation error
    """
    xml_text = body.decode("utf-8")
    related_message_id = None

    try:
        # ── Step 1: Parse XML ──────────────────────────────────────────────
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            print(f"[RECEIVER] ❌ XML parse error: {e}")
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
        if related_message_id and is_duplicate(related_message_id):
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        print(f"[RECEIVER] Received: type={msg_type} | message_id={related_message_id}")

        # ── Step 4: XSD validation ─────────────────────────────────────────
        try:
            validate_xml(xml_text, msg_type)
        except ValueError as e:
            print(f"[RECEIVER] ❌ XSD validation failed for '{msg_type}': {e}")
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

        # ── Step 7: ACK on success ─────────────────────────────────────────
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except ValueError as e:
        code = "unknown_message_type" if "Unknown message type" in str(e) else "invalid_xml_format"
        print(f"[RECEIVER] ❌ {code} for message_id={related_message_id}: {e}")
        send_error_to_queue(code, related_message_id, str(e))
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    except ConnectionError as e:
        print(f"[RECEIVER] ❌ Odoo connection error for message_id={related_message_id}: {e}")
        send_error_to_queue("odoo_api_error", related_message_id, str(e))
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    except Exception as e:
        print(f"[RECEIVER] ❌ Unexpected error for message_id={related_message_id}: {type(e).__name__}: {e}")
        send_error_to_queue("odoo_api_error", related_message_id, str(e))
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


# ── RabbitMQ connection and startup ───────────────────────────────────────────

def connect_to_rabbitmq():
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
    Start the receiver.
    Re-publishes buffered messages on connect (flush_buffer).
    Listens on queue.incoming with prefetch_count=1 for fair dispatch.
    """
    conn = connect_to_rabbitmq()
    channel = conn.channel()

    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.basic_qos(prefetch_count=1)

    flush_buffer()  # re-publish buffered outbox messages after successful connect

    channel.basic_consume(
        queue=QUEUE_NAME,
        on_message_callback=process_message,
    )

    print(f"[RECEIVER] ✓ Listening on queue: {QUEUE_NAME}")
    print(f"[RECEIVER]   Odoo: {ODOO_URL} | DB: {ODOO_DB}")
    print("[RECEIVER]   Waiting for messages… (CTRL+C to stop)")

    channel.start_consuming()


if __name__ == "__main__":
    start_listening()
