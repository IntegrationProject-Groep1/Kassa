"""
sender.py — Publishes outbound messages to RabbitMQ on behalf of the Kassa service.

All messages go through the topic exchange defined by RABBIT_EXCHANGE
(default: kassa.exchange). Each message type maps to a routing key so that
downstream teams can bind their own queues to exactly the events they care about.

Offline buffer:
    When the broker is unreachable, send_message() writes the message to a
    JSON file at OUTBOX_DIR/outbox.json instead of dropping it. The buffer
    holds up to BUFFER_MAX_MESSAGES (500) entries. Once the connection is
    restored, flush_buffer() is called by the receiver on startup and by the
    order poller every 30 seconds to replay any queued messages in order.

Routing key map (see ROUTING_KEYS):
    consumption_order              → kassa.payments.consumption
    payment_registered_consumption → kassa.payments.consumption
    payment_registered_registration→ kassa.payments.registration
    invoice_request                → kassa.payments.invoice
    badge_assigned                 → kassa.payments.badge
    refund_processed               → kassa.payments.refund
    payment_status                 → kassa.frontend.payment
    wallet_balance_update          → kassa.frontend.wallet
    system_error                   → kassa.errors

Public API:
    send_message(routing_key, xml)      — send with an explicit routing key
    send_typed_message(msg_type, xml)   — send using the type→key map above
    flush_buffer()                      — replay buffered messages
    send_error_to_queue(...)            — send a system_error (never buffered)
    build_*_xml(...)                    — XML builder functions
"""

import pika
import json
import os
import time
import threading
import uuid
from pathlib import Path
from datetime import datetime, timezone
# xml.etree.ElementTree (stdlib) is used for building outgoing XML — no extra dependency.
# lxml is used only for XSD schema validation (validate_outgoing), because the stdlib
# ET module has no schema validation support. Both are intentional; do not consolidate.
import xml.etree.ElementTree as ET
import logging
from lxml import etree

from config_utils import parse_rabbit_port


class BufferFullError(RuntimeError):
    """Raised when the outbox buffer has reached its maximum capacity."""


class XSDValidationError(Exception):
    """Raised when an outgoing message fails strict XSD validation."""


logger = logging.getLogger(__name__)


# Configuration
RABBIT_HOST = os.environ.get("RABBIT_HOST")
RABBIT_PORT = parse_rabbit_port()
RABBIT_USER = os.environ.get("RABBIT_USER")
RABBIT_PASS = os.environ.get("RABBIT_PASS")
RABBIT_VHOST = os.environ.get("RABBIT_VHOST", "/")
EXCHANGE_NAME = os.environ.get("RABBIT_EXCHANGE", "kassa.exchange")

# Uptime tracking
_APP_START_TIME = time.monotonic()

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


# Buffer configuration
BUFFER_FILE = Path(os.environ.get("OUTBOX_DIR", "outbox")) / "outbox.json"
BUFFER_MAX_MESSAGES = 500

_buffer_lock = threading.Lock()
_cached_buffer_ids: set[int] = set()
_last_buffer_mtime = 0.0


def _buffer_message(routing_key: str, message_xml: str, record_id: int | None = None, model: str = "pos.order") -> None:
    """
    Append a message to the local JSON outbox when the broker is unreachable.

    record_id and model, when provided, are stored in the entry so that
    flush_buffer() can report which Odoo records were successfully flushed
    and the poller can then write x_rabbitmq_sent=True for them.
    """
    with _buffer_lock:
        entry: dict[str, str | int] = {
            "routing_key": routing_key, "xml": message_xml}
        if record_id is not None:
            entry["record_id"] = record_id
            entry["model"] = model
        entries = _read_buffer()

        if len(entries) >= BUFFER_MAX_MESSAGES:
            send_error_to_queue(
                "offline_queue_full",
                None,
                f"Outbox full: {len(entries)}/{BUFFER_MAX_MESSAGES} — message not buffered: {routing_key}")
            raise BufferFullError(
                f"Outbox buffer full ({BUFFER_MAX_MESSAGES} items) — message not buffered: {routing_key}"
            )

        entries.append(entry)
        BUFFER_FILE.parent.mkdir(parents=True, exist_ok=True)
        BUFFER_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2))
        logger.info(
            f"📁 Buffered message: {routing_key} ({len(entries)}/{BUFFER_MAX_MESSAGES})")


def _read_buffer() -> list:
    """Return all entries from outbox.json, or an empty list if the file does not exist."""
    if not BUFFER_FILE.exists():
        return []
    try:
        return json.loads(BUFFER_FILE.read_text(encoding='utf-8'))
    except Exception as e:
        logger.error(f"Error reading buffer: {e}")
        return []


def flush_buffer() -> list[tuple[str, int]]:
    """
    Replay buffered messages in order, stopping at the first send failure.

    Returns a list of (model, record_id) tuples for entries that were
    successfully flushed, so the caller can update Odoo accordingly.
    """
    with _buffer_lock:
        entries = _read_buffer()
        if not entries:
            return []

    logger.info(f"🔄 Flushing {len(entries)} buffered messages...")
    succeeded = []

    for entry in entries:
        try:
            _publish_or_raise(entry["routing_key"], entry["xml"])
            succeeded.append(entry)
        except Exception as e:
            logger.warning(
                f"⚠️  Buffer resend failed for {entry.get('routing_key', '?')}: {e}")
            break  # Stop on first error, retry later

    with _buffer_lock:
        # Re-read entries in case something was buffered while we were sending
        current_entries = _read_buffer()
        succeeded_xmls = {e["xml"] for e in succeeded}
        remaining = [e for e in current_entries if e["xml"] not in succeeded_xmls]

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

    return [(e["model"], e["record_id"]) for e in succeeded if "record_id" in e and "model" in e]


_connection = None
_channel = None


def connect_to_rabbitmq():
    """
    Return the existing open connection, or open a new one.

    The module-level _connection and _channel are reused across calls so we
    don't open a new TCP connection for every message. If the connection was
    closed (e.g. by a broker restart), a fresh one is created.
    """
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


def _publish_or_raise(routing_key: str, message_xml: str) -> None:
    """Publish with one retry and backoff on transient failures."""
    for attempt in range(2):
        try:
            _, channel = connect_to_rabbitmq()
            channel.basic_publish(
                exchange=EXCHANGE_NAME,
                routing_key=routing_key,
                body=message_xml.encode("utf-8"),
                properties=pika.BasicProperties(delivery_mode=2),
            )
            return
        except (pika.exceptions.AMQPError, OSError, RuntimeError):  # type: ignore[attr-defined]
            global _connection, _channel
            _connection = None
            _channel = None
            if attempt == 1:
                raise
            # Small backoff prevents immediate hammering when broker is unstable.
            time.sleep(0.25)


def setup_exchange(channel):
    """
    Declare the topic exchange.

    The exchange declaration is idempotent — calling it when the exchange
    already exists is harmless.
    """
    channel.exchange_declare(
        exchange=EXCHANGE_NAME,
        exchange_type="topic",
        durable=True
    )


def send_message(
    routing_key: str,
    message_xml: str,
    record_id: int | None = None,
    model: str = "pos.order",
    buffer_on_fail: bool = True
) -> bool:
    """
    Publish xml to kassa.exchange with the given routing_key.

    On any exception the message is written to the local outbox buffer instead of
    being lost, unless buffer_on_fail is set to False.
    Returns True if successfully sent, False if failed (and possibly buffered).
    """
    try:
        _publish_or_raise(routing_key, message_xml)
        logger.info(f"✅ Sent: routing_key={routing_key}")
        return True
    except Exception as e:
        if not buffer_on_fail:
            logger.warning(
                f"⚠️  Send failed ({type(e).__name__}), message discarded (not buffered)")
            return False

        # Buffer on any error (connection refused, timeout, etc.)
        logger.warning(
            f"⚠️  Send failed ({type(e).__name__}), buffering message...")
        _buffer_message(routing_key, message_xml, record_id=record_id, model=model)
        return False


# ── Outgoing XSD validation ────────────────────────────────────────────────────
_SCHEMA_DIR = Path(__file__).parent / "schemas"

_OUTGOING_SCHEMA_MAP = {
    "consumption_order": _SCHEMA_DIR / "schema_consumption_order_v2.3.xsd",
    "payment_registered_consumption": _SCHEMA_DIR / "schema_payment_registered_v2.1.xsd",
    "payment_registered_registration": _SCHEMA_DIR / "schema_payment_registered_v2.1.xsd",
    "refund_processed": _SCHEMA_DIR / "schema_refund_processed.xsd",
    "invoice_request": _SCHEMA_DIR / "schema_invoice_request.xsd",
    "badge_assigned": _SCHEMA_DIR / "schema_badge_assigned.xsd",
    "payment_status": _SCHEMA_DIR / "schema_payment_status.xsd",
    "wallet_balance_update": _SCHEMA_DIR / "schema_wallet_balance_update.xsd",
    "system_error": _SCHEMA_DIR / "schema_error.xsd",
}

# Cache parsed schemas to avoid re-parsing on every message
_schema_cache: dict[str, etree.XMLSchema] = {}


def _validate_outgoing(msg_type: str, message_xml: str) -> None:
    """
    Validate outgoing XML against the corresponding XSD schema.
    Strictly catches both XSD violations and structural XML syntax errors.
    """
    schema_path = _OUTGOING_SCHEMA_MAP.get(msg_type)
    if not schema_path or not schema_path.exists():
        return

    try:
        from defusedxml.lxml import fromstring
        if msg_type not in _schema_cache:
            parser = etree.XMLParser(resolve_entities=False)
            schema_doc = etree.parse(str(schema_path), parser)
            _schema_cache[msg_type] = etree.XMLSchema(schema_doc)

        xml_doc = fromstring(message_xml.encode("utf-8"))
        if not _schema_cache[msg_type].validate(xml_doc):
            errors = str(_schema_cache[msg_type].error_log)
            raise ValueError(f"XSD Validation Error: {errors}")
    except Exception as e:
        if isinstance(e, ValueError):
            raise e
        raise ValueError(f"Unexpected Validation Failure: {str(e)}")


def send_typed_message(
    msg_type: str,
    message_xml: str,
    record_id: int | None = None,
    model: str = "pos.order",
    buffer_on_fail: bool = True
) -> bool:
    """
    Validate against XSD and send the message.
    Strictly blocks the message if XSD validation fails to ensure contract compliance.
    """
    try:
        _validate_outgoing(msg_type, message_xml)
    except ValueError as e:
        # BLOCK the message: Log the detailed XSD error and raise.
        # This prevents invalid XML from reaching RabbitMQ or the offline buffer.

        # BEST PRACTICE: Attempt to extract message_id from the invalid XML for traceability
        related_id = None
        try:
            # We use a non-validating parse just to get the header ID
            from defusedxml import ElementTree as DET
            blocked_root = DET.fromstring(message_xml)
            related_id = blocked_root.findtext(".//message_id")
        except Exception:
            pass

        error_msg = f"XSD validation failed for '{msg_type}': {str(e)}"
        logger.error(
            f"❌ MESSAGE BLOCKED: {error_msg}\n"
            f"Message content (first 500 chars): {message_xml[:500]}..."
        )
        # Send a system_error with the extracted related_id
        send_error_to_queue("invalid_xml_format", related_id, error_msg[:500])
        raise XSDValidationError(error_msg)

    routing_key = ROUTING_KEYS.get(msg_type, f"kassa.misc.{msg_type}")
    return send_message(
        routing_key,
        message_xml,
        record_id=record_id,
        model=model,
        buffer_on_fail=buffer_on_fail
    )


def get_buffered_record_ids(model: str = "pos.order") -> set[int]:
    """Return the set of record IDs currently waiting in the outbox buffer for a given model."""
    with _buffer_lock:
        if not BUFFER_FILE.exists():
            return set()

        # Simple implementation: read all and filter
        entries = _read_buffer()
        return {e["record_id"] for e in entries if e.get("model") == model and "record_id" in e}


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
# ===========================================================================

def build_consumption_order_xml(
    items, customer_id=None, user_id=None,
    customer_type="private",
    email=None, address=None, is_anonymous=False
) -> str:
    """
    Build a consumption_order XML message for a completed POS sale.

    Args:
        items:             List of dicts, each with keys: id, description,
                           quantity, unit_price, vat_rate, currency, item_type.
        customer_id:       Odoo res.partner ID as a string (None for anonymous).
        user_id:           CRM x_user_id (external UUID) of the customer.
        is_company_linked: True if the customer belongs to a company account.
        company_id:        Odoo res.partner ID of the parent company, if any.
        email:             Customer email address.
        address:           Dict of address fields (street, city, zip, country).
        is_anonymous:      True for walk-in / badge-not-found sales. When True
                           the <customer> block is omitted from the XML entirely.
    """
    root = ET.Element("message")
    _make_header(root, "consumption_order")
    body = ET.SubElement(root, "body")
    ET.SubElement(body, "is_anonymous").text = str(is_anonymous).lower()

    if not is_anonymous:
        cust = ET.SubElement(body, "customer")
        ET.SubElement(cust, "id").text = str(customer_id)
        ET.SubElement(cust, "user_id").text = str(user_id) if user_id else ""
        ET.SubElement(cust, "type").text = customer_type
        ET.SubElement(cust, "email").text = str(email) if email else ""
        if address:
            addr = ET.SubElement(cust, "address")
            for k, v in address.items():
                ET.SubElement(addr, k).text = str(v) if v else ""

    items_el = ET.SubElement(body, "items")
    for i in (items or []):
        el = ET.SubElement(items_el, "item")
        ET.SubElement(el, "id").text = str(i["id"])
        ET.SubElement(el, "sku").text = str(i["sku"])
        ET.SubElement(el, "description").text = i["description"]
        ET.SubElement(el, "quantity").text = str(i["quantity"])
        up = ET.SubElement(el, "unit_price")
        up.text = str(i["unit_price"])
        up.set("currency", i.get("currency", "eur"))
        tp = ET.SubElement(el, "total_amount")
        tp.text = f"{i['total_amount']:.2f}"
        tp.set("currency", i.get("currency", "eur"))
        ET.SubElement(el, "vat_rate").text = str(i["vat_rate"])
        if i.get("item_type"):
            ET.SubElement(el, "item_type").text = i["item_type"]

    return _to_xml(root)


def build_payment_registered_xml(
    payment_context, invoice_status, amount_paid,
    due_date, trx_id, payment_method,
    invoice_id=None, user_id=None, correlation_id=None
) -> str:
    """
    Build a payment_registered message confirming a payment was processed.

    Args:
        payment_context: 'consumption' or 'registration' — tells the CRM which
                         flow this payment belongs to.
        invoice_status:  Current invoice state, e.g. 'paid' or 'partial'.
        amount_paid:     Amount actually paid (EUR).
        due_date:        Invoice due date as an ISO-8601 date string.
        trx_id:          Unique transaction ID from the payment terminal.
        payment_method:  How the customer paid, e.g. 'cash', 'card', 'wallet'.
        invoice_id:      Odoo invoice ID, included if available.
        user_id:         CRM x_user_id of the customer, if known.
        correlation_id:  message_id of the original consumption_order, used by
                         the CRM to link this payment back to the sale.
    """
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
    user_id: str, invoice_data: dict, correlation_id: str
) -> str:
    """
    Build an invoice_request message asking the CRM to generate a formal invoice.

    Args:
        user_id:       CRM x_user_id of the customer requesting the invoice.
        invoice_data:  Dict with keys: name, email, address (dict), and
                       optionally vat_number for B2B invoices.
        correlation_id: message_id of the original sale this invoice covers.
    """
    if not correlation_id:
        raise ValueError("correlation_id is required for invoice_request")

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
    ET.SubElement(inv, "email").text = str(invoice_data.get("email") or "")

    addr = ET.SubElement(inv, "address")
    for k, v in invoice_data.get("address", {}).items():
        ET.SubElement(addr, k).text = str(v) if v is not None else ""

    if invoice_data.get("company_name"):
        ET.SubElement(inv, "company_name").text = invoice_data["company_name"]

    if invoice_data.get("vat_number"):
        ET.SubElement(inv, "vat_number").text = invoice_data["vat_number"]

    return _to_xml(root)


def build_badge_assigned_xml(badge_id: str, user_id: str) -> str:
    """
    Build a badge_assigned message notifying the CRM that a badge was linked.

    Args:
        badge_id: Physical badge/RFID identifier (e.g. 'BADGE-RF-00142').
        user_id:  CRM x_user_id of the customer the badge was assigned to.
    """
    root = ET.Element("message")
    _make_header(root, "badge_assigned")
    body = ET.SubElement(root, "body")
    ET.SubElement(body, "user_id").text = user_id
    ET.SubElement(body, "badge_id").text = badge_id
    ET.SubElement(body, "assigned_at").text = now_utc()
    return _to_xml(root)


def build_wallet_balance_update_xml(user_id: str, new_balance: float) -> str:
    """Build wallet_balance_update message"""
    root = ET.Element("message")
    _make_header(root, "wallet_balance_update")
    body = ET.SubElement(root, "body")
    ET.SubElement(body, "user_id").text = str(user_id) if user_id else ""

    bal = ET.SubElement(body, "wallet_balance")
    bal.text = f"{new_balance:.2f}"
    bal.set("currency", "eur")

    return _to_xml(root)


def build_refund_processed_xml(
    original_payment_msg_id: str,
    refund_type: str, refund_amount: float,
    refund_method: str, refund_reason: str,
    original_transaction_id: str,
    user_id=None, description=None, new_wallet_balance=None,
    is_anonymous=False
) -> str:
    """
    Build a refund_processed message confirming a refund was issued.

    Args:
        original_payment_msg_id: message_id of the payment_registered message
                                 being refunded — sent as correlation_id so the
                                 CRM can locate the original transaction.
        refund_type:             'consumption_item' or 'partial'.
        refund_amount:           Amount refunded in EUR.
        refund_method:           How the refund was returned: 'badge_wallet',
                                 'cash', or 'card_reversal'.
        refund_reason:           Canonical reason: 'duplicate_payment',
                                 'customer_request', or 'system_error'.
        original_transaction_id: Terminal transaction ID from the original sale.
        user_id:                 CRM x_user_id if the customer is known.
        description:             Optional longer description of the refund.
        new_wallet_balance:      Updated wallet balance after the refund, if the
                                 refund method was 'badge_wallet'. Included in the XML
                                 so the CRM can update its own balance record.
    """
    root = ET.Element("message")
    _make_header(root, "refund_processed", original_payment_msg_id)
    body = ET.SubElement(root, "body")

    if not is_anonymous and user_id:
        ET.SubElement(body, "user_id").text = user_id

    ET.SubElement(body, "refund_type").text = refund_type

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
    """
    Send a system_error message directly to kassa.errors — without buffering.

    Args:
        error_code:          Short snake_case code, e.g. 'invalid_xml_format',
                             'badge_not_found', 'odoo_api_error'.
        related_message_id:  message_id of the message that caused the error,
                             so the receiving team can correlate it. None if
                             the original message could not be parsed.
        error_description:   Human-readable explanation, truncated to 500 chars.

    Why no buffer: error messages are diagnostic signals, not business data.
    If the broker is down when an error occurs, logging it locally is enough —
    buffering errors and replaying them later would be confusing and could
    arrive out of order relative to the events that caused them.
    """
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
