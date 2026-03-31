"""
Sender — Verstuurt berichten naar RabbitMQ via kassa.exchange
Met lokale buffer (outbox.json) voor offline resilience
Versie 3.4 — Buffer + routing key mapping + error handling
"""

import pika
import json
import os
import uuid
from pathlib import Path
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
import logging

from config_utils import get_env, parse_rabbit_port

logger = logging.getLogger(__name__)


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# Configuration
RABBIT_HOST = get_env("RABBIT_HOST")
RABBIT_PORT = parse_rabbit_port()
RABBIT_USER = get_env("RABBIT_USER")
RABBIT_PASS = get_env("RABBIT_PASS")
RABBIT_VHOST = get_env("RABBIT_VHOST", "/")
RABBIT_AUTO_SETUP_TOPOLOGY = _as_bool(
    get_env("RABBIT_AUTO_SETUP_TOPOLOGY"), default=False
)
EXCHANGE_NAME = os.environ.get("RABBIT_EXCHANGE", "kassa.exchange")

# Routing key mapping
ROUTING_KEYS = {
    "consumption_order": "kassa.payments.consumption",
    "payment_registered_consumption": "kassa.payments.consumption",
    "payment_registered_registration": "kassa.payments.registration",
    "invoice_request": "kassa.payments.invoice",
    "badge_assigned": "kassa.payments.badge",
    "refund_processed": "kassa.payments.refund",
    "payment_status": "kassa.frontend.payment",
    "wallet_balance_update": "kassa.frontend.wallet",
    "system_error": "kassa.errors",
}

# Optional queue topology auto-setup (useful when CRM consumers are not online yet)
OUTBOUND_QUEUE_BINDINGS = {
    "kassa.payments.consumption": os.environ.get(
        "RABBIT_QUEUE_PAYMENTS_CONSUMPTION", "kassa.out.payments.consumption"
    ),
    "kassa.payments.registration": os.environ.get(
        "RABBIT_QUEUE_PAYMENTS_REGISTRATION", "kassa.out.payments.registration"
    ),
    "kassa.payments.refund": os.environ.get(
        "RABBIT_QUEUE_PAYMENTS_REFUND", "kassa.out.payments.refund"
    ),
    "kassa.payments.badge": os.environ.get("RABBIT_QUEUE_PAYMENTS_BADGE", "kassa.out.payments.badge"),
    "kassa.payments.invoice": os.environ.get("RABBIT_QUEUE_PAYMENTS_INVOICE", "kassa.out.payments.invoice"),
    "kassa.frontend.payment": os.environ.get("RABBIT_QUEUE_FRONTEND_PAYMENT", "kassa.out.frontend.payment"),
    "kassa.frontend.wallet": os.environ.get("RABBIT_QUEUE_FRONTEND_WALLET", "kassa.out.frontend.wallet"),
    "kassa.errors": os.environ.get("RABBIT_QUEUE_ERRORS", "kassa.out.errors"),
}

# Buffer configuration
BUFFER_FILE = Path(os.environ.get("OUTBOX_DIR", "outbox")) / "outbox.json"
BUFFER_MAX_MESSAGES = 500


def _buffer_message(routing_key: str, message_xml: str) -> None:
    """Store message in local buffer when RabbitMQ is unavailable"""
    entry = {"routing_key": routing_key, "xml": message_xml}
    entries = _read_buffer()

    if len(entries) >= BUFFER_MAX_MESSAGES:
        logger.warning(
            f"⚠️  Buffer full ({BUFFER_MAX_MESSAGES} items) — message dropped: {routing_key}")
        send_error_to_queue(
            "offline_queue_full",
            None,
            f"Outbox full: {len(entries)}/{BUFFER_MAX_MESSAGES} — message not buffered: {routing_key}")
        return

    entries.append(entry)
    BUFFER_FILE.parent.mkdir(parents=True, exist_ok=True)
    BUFFER_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2))
    logger.info(
        f"📁 Buffered message: {routing_key} ({len(entries)}/{BUFFER_MAX_MESSAGES})")


def _read_buffer() -> list:
    """Read all buffered messages from outbox.json"""
    if not BUFFER_FILE.exists():
        return []
    try:
        return json.loads(BUFFER_FILE.read_text(encoding='utf-8'))
    except Exception as e:
        logger.error(f"Error reading buffer: {e}")
        return []


def flush_buffer() -> None:
    """Resend all buffered messages when connection is restored"""
    entries = _read_buffer()
    if not entries:
        return

    logger.info(f"🔄 Flushing {len(entries)} buffered messages...")
    succeeded = []

    for entry in entries:
        try:
            send_message(entry["routing_key"], entry["xml"])
            succeeded.append(entry)
        except Exception as e:
            logger.warning(
                f"⚠️  Buffer resend failed for {entry.get('routing_key', '?')}: {e}")
            break  # Stop on first error, retry later

    remaining = [e for e in entries if e not in succeeded]

    if remaining:
        BUFFER_FILE.write_text(
            json.dumps(
                remaining,
                ensure_ascii=False,
                indent=2))
    else:
        BUFFER_FILE.unlink(missing_ok=True)

    if succeeded:
        logger.info(
            f"✅ Successfully flushed {len(succeeded)} buffered messages")


_connection = None
_channel = None


def connect_to_rabbitmq():
    """Establish connection to RabbitMQ if not already connected"""
    global _connection, _channel

    if _connection and not _connection.is_closed:
        return _connection, _channel

    credentials = pika.PlainCredentials(RABBIT_USER, RABBIT_PASS)
    params = pika.ConnectionParameters(
        host=RABBIT_HOST,
        port=RABBIT_PORT,
        virtual_host=RABBIT_VHOST,
        credentials=credentials,
        heartbeat=60,
        blocked_connection_timeout=10
    )

    _connection = pika.BlockingConnection(params)
    _channel = _connection.channel()
    setup_exchange(_channel)
    return _connection, _channel


def setup_exchange(channel):
    """Declare the topic exchange"""
    channel.exchange_declare(
        exchange=EXCHANGE_NAME,
        exchange_type="topic",
        durable=True
    )

    if not RABBIT_AUTO_SETUP_TOPOLOGY:
        return

    for routing_key, queue_name in OUTBOUND_QUEUE_BINDINGS.items():
        if not queue_name:
            continue
        try:
            channel.queue_declare(queue=queue_name, durable=True)
            channel.queue_bind(
                exchange=EXCHANGE_NAME,
                queue=queue_name,
                routing_key=routing_key,
            )
        except Exception as exc:
            logger.warning(
                f"⚠️  Could not declare/bind queue '{queue_name}' for '{routing_key}': {exc}"
            )


def send_message(routing_key: str, message_xml: str) -> None:
    """Send message via kassa.exchange using routing key. Buffer on error."""
    global _connection, _channel
    try:
        conn, channel = connect_to_rabbitmq()

        channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key=routing_key,
            body=message_xml.encode("utf-8"),
            properties=pika.BasicProperties(delivery_mode=2)  # Persistent
        )

        logger.info(f"✅ Sent: routing_key={routing_key}")

    except Exception as e:
        # Buffer on any error (connection refused, timeout, etc.)
        logger.warning(
            f"⚠️  Send failed ({type(e).__name__}), buffering message...")
        _connection = None  # Force reconnect on next try
        _channel = None
        _buffer_message(routing_key, message_xml)


def send_typed_message(msg_type: str, message_xml: str) -> None:
    """Send message with automatic routing key selection based on type"""
    routing_key = ROUTING_KEYS.get(msg_type, f"kassa.misc.{msg_type}")
    send_message(routing_key, message_xml)


def now_utc() -> str:
    """ISO-8601 UTC timestamp: YYYY-MM-DDTHH:MM:SSZ"""
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + 'Z'


def _make_header(root, msg_type, correlation_id=None):
    """Build standard message header"""
    header = ET.SubElement(root, "header")
    ET.SubElement(header, "message_id").text = str(uuid.uuid4())
    ET.SubElement(header, "type").text = msg_type
    ET.SubElement(header, "source").text = "kassa"
    ET.SubElement(header, "timestamp").text = now_utc()
    ET.SubElement(header, "version").text = "2.0"
    if correlation_id:
        ET.SubElement(header, "correlation_id").text = correlation_id
    return header


def _to_xml(root) -> str:
    """Convert XML element tree to string"""
    return ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True).decode("utf-8")


# ============================================================================
# Builder Functions — All outgoing message types
# ============================================================================

def build_consumption_order_xml(
    items, customer_id=None, user_id=None,
    is_company_linked=False, company_id=None,
    email=None, address=None, is_anonymous=False
) -> str:
    """Build consumption_order message (POS order with items)"""
    root = ET.Element("message")
    _make_header(root, "consumption_order")
    body = ET.SubElement(root, "body")
    ET.SubElement(body, "is_anonymous").text = str(is_anonymous).lower()

    if not is_anonymous:
        cust = ET.SubElement(body, "customer")
        ET.SubElement(cust, "id").text = str(customer_id)
        ET.SubElement(cust, "user_id").text = str(user_id) if user_id else ""
        ET.SubElement(cust, "is_company_linked").text = str(
            is_company_linked).lower()
        if company_id:
            ET.SubElement(cust, "company_id").text = str(company_id)
        ET.SubElement(cust, "email").text = str(email) if email else ""
        if address:
            addr = ET.SubElement(cust, "address")
            for k, v in address.items():
                ET.SubElement(addr, k).text = str(v) if v else ""

    items_el = ET.SubElement(body, "items")
    for i in (items or []):
        el = ET.SubElement(items_el, "item")
        ET.SubElement(el, "id").text = str(i["id"])
        ET.SubElement(el, "description").text = i["description"]
        ET.SubElement(el, "quantity").text = str(i["quantity"])
        up = ET.SubElement(el, "unit_price")
        up.text = str(i["unit_price"])
        up.set("currency", i.get("currency", "eur"))
        ET.SubElement(el, "vat_rate").text = str(i["vat_rate"])
        if i.get("item_type"):
            ET.SubElement(el, "item_type").text = i["item_type"]

    return _to_xml(root)


def build_payment_registered_xml(
    payment_context, invoice_status, amount_paid,
    due_date, trx_id, payment_method,
    invoice_id=None, user_id=None, correlation_id=None
) -> str:
    """Build payment_registered message (payment confirmed)"""
    root = ET.Element("message")
    _make_header(root, "payment_registered", correlation_id)
    body = ET.SubElement(root, "body")
    ET.SubElement(body, "payment_context").text = payment_context

    if user_id:
        ET.SubElement(body, "user_id").text = user_id

    inv = ET.SubElement(body, "invoice")
    if invoice_id:
        ET.SubElement(inv, "id").text = invoice_id
    ET.SubElement(inv, "status").text = invoice_status

    ap = ET.SubElement(inv, "amount_paid")
    ap.text = str(amount_paid)
    ap.set("currency", "eur")
    ET.SubElement(inv, "due_date").text = due_date

    trx = ET.SubElement(body, "transaction")
    ET.SubElement(trx, "id").text = trx_id
    ET.SubElement(trx, "payment_method").text = payment_method

    return _to_xml(root)


def build_invoice_request_xml(
    user_id: str, invoice_data: dict, correlation_id=None
) -> str:
    """Build invoice_request message"""
    root = ET.Element("message")
    _make_header(root, "invoice_request", correlation_id)
    body = ET.SubElement(root, "body")
    ET.SubElement(body, "user_id").text = user_id

    inv = ET.SubElement(body, "invoice_data")

    first_name = invoice_data.get("first_name")
    last_name = invoice_data.get("last_name")

    # Backward-compatible fallback for callers still passing a single full name.
    if (not first_name or not last_name) and invoice_data.get("name"):
        full_name = str(invoice_data["name"]).strip()
        parts = full_name.split(maxsplit=1)
        if not first_name and parts:
            first_name = parts[0]
        if not last_name:
            last_name = parts[1] if len(parts) > 1 else ""

    ET.SubElement(inv, "first_name").text = str(first_name or "")
    ET.SubElement(inv, "last_name").text = str(last_name or "")
    ET.SubElement(inv, "email").text = invoice_data["email"]

    addr = ET.SubElement(inv, "address")
    for k, v in invoice_data.get("address", {}).items():
        ET.SubElement(addr, k).text = str(v) if v is not None else ""

    if invoice_data.get("vat_number"):
        ET.SubElement(inv, "vat_number").text = invoice_data["vat_number"]

    return _to_xml(root)


def build_badge_assigned_xml(badge_id: str, user_id: str) -> str:
    """Build badge_assigned message"""
    root = ET.Element("message")
    _make_header(root, "badge_assigned")
    body = ET.SubElement(root, "body")
    ET.SubElement(body, "badge_id").text = badge_id
    ET.SubElement(body, "user_id").text = user_id
    ET.SubElement(body, "assigned_at").text = now_utc()
    return _to_xml(root)


def build_refund_processed_xml(
    original_payment_msg_id: str,
    refund_type: str, refund_amount: float,
    refund_method: str, refund_reason: str,
    original_transaction_id: str,
    user_id=None, description=None, new_wallet_balance=None
) -> str:
    """Build refund_processed message"""
    root = ET.Element("message")
    _make_header(root, "refund_processed", original_payment_msg_id)
    body = ET.SubElement(root, "body")
    ET.SubElement(body, "refund_type").text = refund_type

    if user_id:
        ET.SubElement(body, "user_id").text = user_id

    refund = ET.SubElement(body, "refund")
    amt = ET.SubElement(refund, "amount")
    amt.text = str(refund_amount)
    amt.set("currency", "eur")
    ET.SubElement(refund, "method").text = refund_method
    ET.SubElement(refund, "reason").text = refund_reason

    if description:
        ET.SubElement(refund, "description").text = description

    ET.SubElement(
        body,
        "original_transaction_id").text = original_transaction_id

    if new_wallet_balance is not None:
        wb = ET.SubElement(body, "new_wallet_balance")
        wb.text = f"{new_wallet_balance:.2f}"
        wb.set("currency", "eur")

    return _to_xml(root)


def send_error_to_queue(
    error_code: str, related_message_id: str | None, error_description: str
) -> None:
    """Send system_error message to kassa.errors queue. Does not buffer on failure."""
    root = ET.Element("message")
    _make_header(root, "system_error")
    body = ET.SubElement(root, "body")
    ET.SubElement(body, "error_code").text = error_code.lower()

    if related_message_id:
        ET.SubElement(body, "related_message_id").text = related_message_id

    ET.SubElement(body, "error_description").text = error_description[:500]

    error_xml = _to_xml(root)

    try:
        conn, channel = connect_to_rabbitmq()

        channel.basic_publish(
            exchange=EXCHANGE_NAME,
            routing_key="kassa.errors",
            body=error_xml.encode("utf-8"),
            properties=pika.BasicProperties(delivery_mode=2)  # Persistent
        )
    except Exception as err:
        logger.error(
            f"❌ Could not send error message to RabbitMQ (it will not be buffered): {err}")
