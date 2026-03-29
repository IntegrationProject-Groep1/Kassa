# test_sender.py – Local test simulator for receiver.py
# Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026
#
# Usage: python test_sender.py [message_type]
#
# Examples:
#   python test_sender.py new_registration
#   python test_sender.py profile_update
#   python test_sender.py badge_scanned
#   python test_sender.py cancel_registration
#   python test_sender.py all   (sends all 4 types)
#
# Requires a local RabbitMQ – start with:
#   docker run -d --name rabbitmq -p 5672:5672 rabbitmq:3

import os
import sys
import uuid
import pika
from datetime import datetime, timezone


def _parse_rabbit_port() -> int:
    value = os.environ.get("RABBIT_PORT")
    try:
        return int(value) if value else 5672
    except ValueError:
        return 5672


# ── RabbitMQ connection (local or via .env) ────────────────────────────────────
RABBIT_HOST = os.environ.get("RABBIT_HOST", "localhost")
RABBIT_PORT = _parse_rabbit_port()
RABBIT_VHOST = os.environ.get("RABBIT_VHOST", "/")
RABBIT_USER = os.environ.get("RABBIT_USER", "guest")
RABBIT_PASS = os.environ.get("RABBIT_PASS", "guest")
QUEUE_NAME = os.environ.get("RABBIT_INCOMING_QUEUE", "kassa.incoming")


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def send(xml_text: str, label: str) -> None:
    try:
        credentials = pika.PlainCredentials(RABBIT_USER, RABBIT_PASS)
        params = pika.ConnectionParameters(
            host=RABBIT_HOST,
            port=RABBIT_PORT,
            virtual_host=RABBIT_VHOST,
            credentials=credentials,
        )
        conn = pika.BlockingConnection(params)
        channel = conn.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        channel.basic_publish(
            exchange="",
            routing_key=QUEUE_NAME,
            body=xml_text.encode("utf-8"),
            properties=pika.BasicProperties(delivery_mode=2),
        )
        conn.close()
        print(f"[TEST_SENDER] ✓ Sent: {label}")
        print(f"[TEST_SENDER]   To queue: {QUEUE_NAME} on {RABBIT_HOST}")
    except Exception as e:
        print(f"[TEST_SENDER] ✗ Error sending '{label}': {e}")
        print(f"[TEST_SENDER]   Tip: make sure RabbitMQ is reachable on {RABBIT_HOST}:{RABBIT_PORT}")
        print(f"[TEST_SENDER]   Current vhost: {RABBIT_VHOST}")


# ── XML builders for all 4 message types ──────────────────────────────────────

def build_new_registration(company: bool = False) -> str:
    msg_id = str(uuid.uuid4())
    if company:
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>{msg_id}</message_id>
    <type>new_registration</type>
    <source>crm</source>
    <timestamp>{now_utc()}</timestamp>
    <version>2.0</version>
  </header>
  <body>
    <customer>
      <email>info@techbedrijf.be</email>
      <name>Jan Peeters</name>
      <company_name>TechCompany NV</company_name>
      <type>company</type>
      <vat_number>BE0123456789</vat_number>
      <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
      <age>35</age>
    </customer>
    <payment_due>
      <amount>50.00</amount>
      <status>unpaid</status>
    </payment_due>
  </body>
</message>"""
    else:
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>{msg_id}</message_id>
    <type>new_registration</type>
    <source>crm</source>
    <timestamp>{now_utc()}</timestamp>
    <version>2.0</version>
  </header>
  <body>
    <customer>
      <email>sophie@gmail.com</email>
      <name>Sophie Martens</name>
      <type>private</type>
      <user_id>a1b2c3d4-1111-2222-3333-444455556666</user_id>
      <age>28</age>
    </customer>
    <payment_due>
      <amount>25.00</amount>
      <status>unpaid</status>
    </payment_due>
  </body>
</message>"""


def build_profile_update() -> str:
    msg_id = str(uuid.uuid4())
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>{msg_id}</message_id>
    <type>profile_update</type>
    <source>crm</source>
    <timestamp>{now_utc()}</timestamp>
    <version>2.0</version>
  </header>
  <body>
    <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
    <email>nieuw@techbedrijf.be</email>
    <name>Jan Peeters</name>
    <company_name>TechCompany NV (Hernoemd)</company_name>
    <age>36</age>
    <type>company</type>
    <vat_number>BE0123456789</vat_number>
  </body>
</message>"""


def build_badge_scanned(known: bool = True) -> str:
    msg_id = str(uuid.uuid4())
    badge = "BADGE-RF-00142" if known else "BADGE-RF-99999"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>{msg_id}</message_id>
    <type>badge_scanned</type>
    <source>iot_scanner_bar</source>
    <timestamp>{now_utc()}</timestamp>
    <version>2.0</version>
  </header>
  <body>
    <badge_id>{badge}</badge_id>
    <location>hoofdbar</location>
  </body>
</message>"""


def build_cancel_registration() -> str:
    msg_id = str(uuid.uuid4())
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>{msg_id}</message_id>
    <type>cancel_registration</type>
    <source>crm</source>
    <timestamp>{now_utc()}</timestamp>
    <version>2.0</version>
  </header>
  <body>
    <user_id>a1b2c3d4-1111-2222-3333-444455556666</user_id>
    <session_id>session-uuid-001</session_id>
  </body>
</message>"""


def build_invalid_xml() -> str:
    """Simulate a corrupt message for sad-path testing."""
    return "this is not valid xml <<<"


def build_unknown_type() -> str:
    """Simulate an unknown message type."""
    msg_id = str(uuid.uuid4())
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>{msg_id}</message_id>
    <type>unknown_type</type>
    <source>test</source>
    <timestamp>{now_utc()}</timestamp>
    <version>2.0</version>
  </header>
  <body><data>test</data></body>
</message>"""


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"

    print(f"\n[TEST_SENDER] RabbitMQ: {RABBIT_HOST} | Queue: {QUEUE_NAME}")
    print(f"[TEST_SENDER] Mode: {arg}\n")

    if arg in ("new_registration", "all"):
        send(build_new_registration(company=False), "new_registration (private)")
        send(build_new_registration(company=True), "new_registration (company)")

    if arg in ("profile_update", "all"):
        send(build_profile_update(), "profile_update")

    if arg in ("badge_scanned", "all"):
        send(build_badge_scanned(known=True), "badge_scanned (known badge)")
        send(build_badge_scanned(known=False), "badge_scanned (unknown badge – sad path)")

    if arg in ("cancel_registration", "all"):
        send(build_cancel_registration(), "cancel_registration")

    if arg in ("sad_paths", "all"):
        send(build_invalid_xml(), "invalid XML (sad path)")
        send(build_unknown_type(), "unknown message type (sad path)")

    print("\n[TEST_SENDER] Done. Check the logs of receiver.py.")
