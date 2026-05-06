# simulate_receiver_input.py – Local test simulator for receiver.py
# Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026
#
# Usage: python simulate_receiver_input.py [message_type]
#
# Examples:
#   python simulate_receiver_input.py new_registration
#   python simulate_receiver_input.py profile_update
#   python simulate_receiver_input.py badge_scanned
#   python simulate_receiver_input.py cancel_registration
#   python simulate_receiver_input.py all   (sends all 4 types)
#
# Requires a local RabbitMQ – start with:
#   docker run -d --name rabbitmq -p 5672:5672 rabbitmq:3

import os
import sys
import uuid
import pika
from datetime import datetime, timezone

from config_utils import parse_rabbit_port


# ── RabbitMQ connection (local or via .env) ────────────────────────────────────
RABBIT_HOST = os.environ.get("RABBIT_HOST", "localhost")
RABBIT_PORT = parse_rabbit_port()
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
        print(f"[SIMULATE] ✓ Sent: {label}")
        print(f"[SIMULATE]   To queue: {QUEUE_NAME} on {RABBIT_HOST}")
    except Exception as e:
        print(f"[SIMULATE] ✗ Error sending '{label}': {e}")
        print(f"[SIMULATE]   Tip: make sure RabbitMQ is reachable on {RABBIT_HOST}:{RABBIT_PORT}")
        print(f"[SIMULATE]   Current vhost: {RABBIT_VHOST}")


# ── XML builders for all 4 message types ──────────────────────────────────────

def build_new_registration(company: bool = False) -> str:
    msg_id = str(uuid.uuid4())
    timestamp = now_utc()
    if company:
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>{msg_id}</message_id>
    <timestamp>{timestamp}</timestamp>
    <source>crm</source>
    <type>new_registration</type>
    <version>2.0</version>
  </header>
  <body>
    <customer>
      <email>info@techbedrijf.be</email>
      <type>company</type>
      <company_name>TechCompany NV</company_name>
      <vat_number>BE0123456789</vat_number>
      <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
      <payment_due>
        <amount>50.00</amount>
        <status>paid</status>
      </payment_due>
    </customer>
  </body>
</message>"""
    else:
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>{msg_id}</message_id>
    <timestamp>{timestamp}</timestamp>
    <source>crm</source>
    <type>new_registration</type>
    <version>2.0</version>
  </header>
  <body>
    <customer>
      <email>sophie@gmail.com</email>
      <contact>
        <first_name>Sophie</first_name>
        <last_name>Martens</last_name>
      </contact>
      <type>private</type>
      <user_id>a1b2c3d4-1111-2222-3333-444455556666</user_id>
      <date_of_birth>1998-05-15</date_of_birth>
      <payment_due>
        <amount>25.00</amount>
        <status>unpaid</status>
      </payment_due>
    </customer>
  </body>
</message>"""


def build_profile_update() -> str:
    msg_id = str(uuid.uuid4())
    timestamp = now_utc()
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>{msg_id}</message_id>
    <timestamp>{timestamp}</timestamp>
    <source>crm</source>
    <type>profile_update</type>
    <version>2.0</version>
  </header>
  <body>
    <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
    <email>nieuw@techbedrijf.be</email>
    <contact>
      <first_name>Jan</first_name>
      <last_name>Peeters</last_name>
    </contact>
    <company_name>TechCompany NV (Hernoemd)</company_name>
    <date_of_birth>1985-05-15</date_of_birth>
    <type>company</type>
    <vat_number>BE0123456789</vat_number>
    <payment_due>
      <amount>0.00</amount>
      <status>paid</status>
    </payment_due>
  </body>
</message>"""


def build_badge_scanned(known: bool = True) -> str:
    msg_id = str(uuid.uuid4())
    timestamp = now_utc()
    badge = "BADGE-RF-00142" if known else "BADGE-RF-99999"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>{msg_id}</message_id>
    <timestamp>{timestamp}</timestamp>
    <source>iot_gateway</source>
    <type>badge_scanned</type>
    <version>2.0</version>
  </header>
  <body>
    <badge_id>{badge}</badge_id>
    <location>bar</location>
    <scanned_at>{timestamp}</scanned_at>
  </body>
</message>"""


def build_cancel_registration() -> str:
    msg_id = str(uuid.uuid4())
    timestamp = now_utc()
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>{msg_id}</message_id>
    <timestamp>{timestamp}</timestamp>
    <source>crm</source>
    <type>cancel_registration</type>
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
    timestamp = now_utc()
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>{msg_id}</message_id>
    <timestamp>{timestamp}</timestamp>
    <source>test</source>
    <type>unknown_type</type>
    <version>2.0</version>
  </header>
  <body><data>test</data></body>
</message>"""


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"

    print(f"\n[SIMULATE] RabbitMQ: {RABBIT_HOST} | Queue: {QUEUE_NAME}")
    print(f"[SIMULATE] Mode: {arg}\n")

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

    print("\n[SIMULATE] Done. Check the logs of receiver.py.")
