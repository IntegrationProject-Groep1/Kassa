"""
Integration test runner for receiver.py
Tests: new_registration flow (create, idempotency, XSD failure)
Run inside the kassa-integratie container:
  python run_integration_tests.py
"""
import os
import sys
import time
import uuid
import pika
import xmlrpc.client  # nosec

# Allow importing config_utils from the integratie/ root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config_utils import parse_rabbit_port  # noqa: E402

# ── RabbitMQ config ────────────────────────────────────────────────────────────
RABBIT_HOST = os.environ.get("RABBIT_HOST", "localhost")
RABBIT_PORT = parse_rabbit_port()
RABBIT_VHOST = os.environ.get("RABBIT_VHOST", "/")
RABBIT_USER = os.environ.get("RABBIT_USER", "guest")
RABBIT_PASS = os.environ.get("RABBIT_PASS", "guest")
QUEUE_NAME = os.environ.get("RABBIT_INCOMING_QUEUE", "kassa.incoming")

# ── Odoo config ────────────────────────────────────────────────────────────────
ODOO_URL = os.environ.get("ODOO_URL", "http://kassa-web:8069")
ODOO_DB = os.environ.get("ODOO_DB", "odoo_kassa")
ODOO_USER = os.environ.get("ODOO_USER", "odoo")
ODOO_PASS = os.environ.get("ODOO_PASS", "myodoo")

# ── Test identity (unique per run) ─────────────────────────────────────────────
TEST_USER_ID = f"kassa-test-{uuid.uuid4()}"
TEST_MESSAGE_ID = str(uuid.uuid4())
NOW = "2026-03-30T13:00:00Z"

RESULTS = []


# ── Helpers ────────────────────────────────────────────────────────────────────

def publish(xml_text: str, label: str) -> None:
    creds = pika.PlainCredentials(RABBIT_USER, RABBIT_PASS)
    params = pika.ConnectionParameters(
        host=RABBIT_HOST, port=RABBIT_PORT,
        virtual_host=RABBIT_VHOST, credentials=creds,
    )
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    # BEST PRACTICE: Publish to the exchange using the correct routing key
    # instead of declaring the queue directly, which avoids 406 Precondition Failed
    # errors if the test runner's queue args don't match the broker's.
    ch.basic_publish(
        exchange="kassa.exchange",
        routing_key="kassa.incoming.registration",  # Correct key for registration
        body=xml_text.encode("utf-8"),
        properties=pika.BasicProperties(delivery_mode=2),
    )
    conn.close()
    print(f"  [SENT] {label}")


def odoo_count(user_id: str) -> int:
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASS, {})
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    ids: list = models.execute_kw(  # type: ignore[assignment]
        ODOO_DB, uid, ODOO_PASS,
        "res.partner", "search",
        [[["x_user_id", "=", user_id]]],
    )
    return len(ids)


def odoo_get_partner(user_id: str) -> dict | None:
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASS, {})
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    results: list = models.execute_kw(  # type: ignore[assignment]
        ODOO_DB, uid, ODOO_PASS,
        "res.partner", "search_read",
        [[["x_user_id", "=", user_id]]],
        {"fields": ["id", "name", "email", "x_user_id", "x_date_of_birth", "is_company", "x_session_id"], "limit": 1},
    )
    return results[0] if results else None


def wait(seconds: int, reason: str) -> None:
    print(f"  [WAIT] {seconds}s — {reason}")
    time.sleep(seconds)


def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ── XML builders (conforming to schema_nieuwe_inschrijving.xsd) ────────────────

def build_valid_registration(message_id: str, user_id: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>{message_id}</message_id>
    <type>new_registration</type>
    <source>crm</source>
    <timestamp>2026-03-30T13:00:00Z</timestamp>
    <version>2.0</version>
  </header>
  <body>
    <customer>
      <user_id>{user_id}</user_id>
      <email>kassa.testuser@test.be</email>
      <date_of_birth>1996-01-01</date_of_birth>
      <contact>
        <first_name>Kassa</first_name>
        <last_name>TestUser</last_name>
      </contact>
      <type>private</type>
      <session_id>sess-test-001</session_id>
      <payment_due>
        <amount currency="eur">25.00</amount>
        <status>unpaid</status>
      </payment_due>
    </customer>
  </body>
</message>"""


def build_invalid_registration_missing_contact() -> str:
    """Valid XML but fails XSD: missing required <contact> and <payment_due>."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>{uuid.uuid4()}</message_id>
    <type>new_registration</type>
    <source>crm</source>
    <timestamp>2026-03-30T13:00:00Z</timestamp>
    <version>2.0</version>
  </header>
  <body>
    <customer>
      <email>broken@test.be</email>
      <type>private</type>
      <user_id>broken-user-no-contact</user_id>
      <date_of_birth>2001-01-01</date_of_birth>
    </customer>
  </body>
</message>"""


# ── Test 1: Valid new_registration ─────────────────────────────────────────────

def test1_valid_registration():
    section("TEST 1 — Valid new_registration (new client)")
    print(f"  TEST_USER_ID  : {TEST_USER_ID}")
    print(f"  TEST_MESSAGE_ID: {TEST_MESSAGE_ID}")

    xml = build_valid_registration(TEST_MESSAGE_ID, TEST_USER_ID)
    publish(xml, "new_registration (valid, new client)")
    wait(4, "receiver processes message")

    partner = odoo_get_partner(TEST_USER_ID)
    count = odoo_count(TEST_USER_ID)

    print("\n  Odoo result:")
    print(f"    Partners found : {count}")
    if partner:
        print(f"    id             : {partner['id']}")
        print(f"    name           : {partner['name']}")
        print(f"    email          : {partner['email']}")
        print(f"    x_user_id      : {partner['x_user_id']}")
        print(f"    x_date_of_birth: {partner['x_date_of_birth']}")
        print(f"    is_company     : {partner['is_company']}")

    ok = (
        count == 1
        and partner is not None
        and partner["name"] == "Kassa TestUser"
        and partner["email"] == "kassa.testuser@test.be"
        and partner["x_user_id"] == TEST_USER_ID
        and partner["x_date_of_birth"] == "1996-01-01"
        and partner["is_company"] is False
    )
    result = "PASS" if ok else "FAIL"
    reason = "All Odoo fields match" if ok else (
        f"count={count}, name={partner['name'] if partner else 'N/A'}, "
        f"email={partner['email'] if partner else 'N/A'}"
    )
    print(f"\n  RESULT: {result} — {reason}")
    RESULTS.append(("Test 1 — Valid new_registration", result, reason))


# ── Test 2: Idempotency ────────────────────────────────────────────────────────

def test2_idempotency():
    section("TEST 2 — Idempotency (same message_id sent twice)")
    print(f"  Resending message_id: {TEST_MESSAGE_ID}")

    xml = build_valid_registration(TEST_MESSAGE_ID, TEST_USER_ID)
    publish(xml, "new_registration (duplicate message_id)")
    wait(4, "receiver processes (should skip as duplicate)")

    count = odoo_count(TEST_USER_ID)
    print(f"\n  Partners with x_user_id={TEST_USER_ID}: {count}")

    ok = count == 1
    result = "PASS" if ok else "FAIL"
    reason = "Still exactly 1 partner (duplicate blocked)" if ok else f"Expected 1, got {count}"
    print(f"\n  RESULT: {result} — {reason}")
    RESULTS.append(("Test 2 — Idempotency", result, reason))


# ── Test 3: Invalid XML (XSD validation failure) ───────────────────────────────

def test3_invalid_xml():
    section("TEST 3 — XSD validation failure (missing <contact> and <payment_due>)")

    xml = build_invalid_registration_missing_contact()
    publish(xml, "new_registration (invalid — missing required XSD fields)")
    wait(4, "receiver processes (should reject with invalid_xml_format)")

    # Nothing should be created for broken-user-no-contact
    count = odoo_count("broken-user-no-contact")
    print(f"\n  Partners created for broken-user-no-contact: {count}")

    ok = count == 0
    result = "PASS" if ok else "FAIL"
    reason = "No partner created (message rejected)" if ok else f"Expected 0 partners, got {count}"
    print(f"\n  RESULT: {result} — {reason}")
    RESULTS.append(("Test 3 — XSD validation failure", result, reason))


# ── Summary ────────────────────────────────────────────────────────────────────

def summary():
    section("SUMMARY")
    all_pass = True
    for name, result, reason in RESULTS:
        icon = "✅" if result == "PASS" else "❌"
        print(f"  {icon} {result}  {name}")
        print(f"         {reason}")
        if result != "PASS":
            all_pass = False
    print(f"\n  Overall: {'ALL PASS ✅' if all_pass else 'SOME TESTS FAILED ❌'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print("  KASSA INTEGRATION TEST — receiver.py new_registration flow")
    print(f"{'='*60}")
    print(f"  RabbitMQ : {RABBIT_HOST}:{RABBIT_PORT} vhost={RABBIT_VHOST}")
    print(f"  Queue    : {QUEUE_NAME}")
    print(f"  Odoo     : {ODOO_URL} db={ODOO_DB}")

    test1_valid_registration()
    test2_idempotency()
    test3_invalid_xml()

    sys.exit(summary())
