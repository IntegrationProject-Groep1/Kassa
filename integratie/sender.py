# sender.py – v3.4
# Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026
#
# Publishes outgoing messages to RabbitMQ.
# Provides:
#   - send_error_to_queue  → publish system_error XML to queue.error
#   - flush_buffer         → re-publish buffered messages after reconnect
#   - now_utc              → ISO-8601 UTC timestamp helper

import os
import uuid
from collections import deque
from datetime import datetime, timezone

import pika

# ── Environment ────────────────────────────────────────────────────────────────
RABBIT_HOST  = os.environ.get("RABBIT_HOST")
RABBIT_PORT  = int(os.environ.get("RABBIT_PORT", 5672))
RABBIT_VHOST = os.environ.get("RABBIT_VHOST", "/")
RABBIT_USER  = os.environ.get("RABBIT_USER")
RABBIT_PASS  = os.environ.get("RABBIT_PASS")

ERROR_QUEUE = "queue.error"
SOURCE      = "kassa"

# ── Outbox buffer (in-memory) ──────────────────────────────────────────────────
# Used when RabbitMQ is temporarily unreachable.
# Heartbeats are never buffered (per spec).
MAX_BUFFER_SIZE = 1_000
_outbox_buffer: deque = deque()


# ── Helpers ────────────────────────────────────────────────────────────────────

def now_utc() -> str:
    """Return current UTC time as ISO-8601 string (e.g. 2026-03-28T12:00:00Z)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def _build_error_xml(
    error_code: str,
    related_message_id: str | None,
    description: str,
) -> str:
    msg_id  = str(uuid.uuid4())
    related = related_message_id or ""
    # Escape characters that are illegal in XML text content
    description = (
        description
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<message>\n"
        "  <header>\n"
        f"    <message_id>{msg_id}</message_id>\n"
        "    <type>system_error</type>\n"
        f"    <source>{SOURCE}</source>\n"
        f"    <timestamp>{now_utc()}</timestamp>\n"
        "    <version>2.0</version>\n"
        "  </header>\n"
        "  <body>\n"
        f"    <error_code>{error_code}</error_code>\n"
        f"    <related_message_id>{related}</related_message_id>\n"
        f"    <description>{description}</description>\n"
        "  </body>\n"
        "</message>"
    )


def _publish(xml_text: str, queue: str) -> None:
    """Open a connection, publish one message, then close."""
    credentials = pika.PlainCredentials(RABBIT_USER, RABBIT_PASS)
    params      = pika.ConnectionParameters(host=RABBIT_HOST, port=RABBIT_PORT, virtual_host=RABBIT_VHOST, credentials=credentials)
    conn        = pika.BlockingConnection(params)
    channel     = conn.channel()
    channel.queue_declare(queue=queue, durable=True)
    channel.basic_publish(
        exchange="",
        routing_key=queue,
        body=xml_text.encode("utf-8"),
        properties=pika.BasicProperties(delivery_mode=2),
    )
    conn.close()


# ── Public API ─────────────────────────────────────────────────────────────────

def send_error_to_queue(
    error_code: str,
    related_message_id: str | None,
    error_description: str,
) -> None:
    """
    Build a system_error XML message and publish it to queue.error.
    If RabbitMQ is unreachable the message is saved to the outbox buffer.
    """
    xml_text = _build_error_xml(error_code, related_message_id, error_description)
    try:
        _publish(xml_text, ERROR_QUEUE)
        print(f"[SENDER] ✓ Error sent: {error_code} | related={related_message_id}")
    except Exception as exc:
        print(f"[SENDER] ⚠ Could not send error – buffering: {exc}")
        if len(_outbox_buffer) < MAX_BUFFER_SIZE:
            _outbox_buffer.append((xml_text, ERROR_QUEUE))


def flush_buffer() -> None:
    """
    Re-publish all buffered outbox messages.
    Called by receiver.start_listening() after a successful RabbitMQ connect.
    """
    if not _outbox_buffer:
        return

    print(f"[SENDER] Flushing {len(_outbox_buffer)} buffered message(s)…")
    failed: deque = deque()
    flushed = 0

    while _outbox_buffer:
        xml_text, queue = _outbox_buffer.popleft()
        try:
            _publish(xml_text, queue)
            flushed += 1
        except Exception as exc:
            print(f"[SENDER] ⚠ Flush failed – re-buffering: {exc}")
            failed.append((xml_text, queue))

    _outbox_buffer.extend(failed)

    if flushed:
        print(f"[SENDER] ✓ Flushed {flushed} message(s)")
