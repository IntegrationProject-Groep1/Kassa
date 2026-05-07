"""
run_integration_tests.py — Comprehensive Integration Test Suite
Covers 10+ distinct scenarios across all 8 core flows.
"""
import os
import sys
import time
import uuid
import pika
import xmlrpc.client  # nosec


# Allow importing config_utils from the integratie/ root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config_utils import get_env, parse_rabbit_port  # noqa: E402


# ── Config ─────────────────────────────────────────────────────────────────────
ODOO_URL = get_env("ODOO_URL", "http://kassa-web:8069")
ODOO_DB = get_env("ODOO_DB", "odoo_kassa")
ODOO_USER = get_env("ODOO_USER", "odoo")
ODOO_PASS = get_env("ODOO_PASS", "myodoo")

RABBIT_HOST = get_env("RABBIT_HOST", "localhost")
RABBIT_PORT = parse_rabbit_port()
RABBIT_VHOST = get_env("RABBIT_VHOST", "/")
RABBIT_USER = get_env("RABBIT_USER", "guest")
RABBIT_PASS = get_env("RABBIT_PASS", "guest")
EXCHANGE_NAME = "kassa.exchange"

# ── Test state ─────────────────────────────────────────────────────────────────
TEST_ID = uuid.uuid4().hex[:8]
TEST_USER_ID = f"kassa-test-{TEST_ID}"
TEST_BADGE_ID = f"BADGE-{TEST_ID.upper()}"
RESULTS = []
GLOBAL_SESSION_ID = None


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_rpc():
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASS, {})
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
    return uid, models


def publish(xml_text: str, routing_key: str):
    creds = pika.PlainCredentials(RABBIT_USER, RABBIT_PASS)
    params = pika.ConnectionParameters(
        host=RABBIT_HOST, port=RABBIT_PORT,
        virtual_host=RABBIT_VHOST, credentials=creds,
    )
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    ch.basic_publish(exchange=EXCHANGE_NAME, routing_key=routing_key, body=xml_text.encode("utf-8"))
    conn.close()


def wait(seconds=4, label="processing"):
    print(f"  [WAIT] {seconds}s — {label}")
    time.sleep(seconds)


def section(title):
    print(f"\n{'='*70}\n  {title}\n{'='*70}")


def report_result(name, ok, reason=""):
    res = "PASS" if ok else "FAIL"
    print(f"\n  RESULT: {res} — {reason}")
    RESULTS.append((name, res, reason))


def ensure_opened_session(uid, models):
    """Ensure at least one POS session is opened for testing."""
    global GLOBAL_SESSION_ID
    if GLOBAL_SESSION_ID:
        return GLOBAL_SESSION_ID

    # 1. Try to find any already opened session (any config)
    session_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "pos.session", "search",
        [[["state", "=", "opened"]]], {"limit": 1}
    )
    if session_ids:
        print(f"  [ODOO] Reusing existing opened session: {session_ids[0]}")
        GLOBAL_SESSION_ID = session_ids[0]
        return GLOBAL_SESSION_ID

    # 2. Resolve target config
    config_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "pos.config", "search",
        [[["name", "=", "Bar Kassa"]]], {"limit": 1}
    )
    if not config_ids:
        config_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.config", "search", [[]], {"limit": 1})
    config_id = config_ids[0]

    # 3. Look for ANY non-closed session for this config
    existing_session_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "pos.session", "search",
        [[["config_id", "=", config_id], ["state", "!=", "closed"]]], {"limit": 1}
    )

    if existing_session_ids:
        session_id = existing_session_ids[0]
        # Try to push it to 'opened' state
        try:
            models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.session", "action_pos_session_open", [[session_id]])
        except Exception:
            pass
        GLOBAL_SESSION_ID = session_id
        return GLOBAL_SESSION_ID

    # 4. Create new session only if none exists
    try:
        session_id = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS, "pos.session", "create",
            [{"config_id": config_id, "user_id": uid}]
        )
        models.execute_kw(
            ODOO_DB, uid, ODOO_PASS, "pos.session",
            "action_pos_session_open", [[session_id]]
        )
        print(f"  [ODOO] Created and opened new POS session: {session_id}")
        GLOBAL_SESSION_ID = session_id
        return GLOBAL_SESSION_ID
    except Exception as e:
        if "Another session is already opened" in str(e):
            retry_ids = models.execute_kw(
                ODOO_DB, uid, ODOO_PASS, "pos.session", "search",
                [[["config_id", "=", config_id], ["state", "!=", "closed"]]], {"limit": 1}
            )
            if retry_ids:
                GLOBAL_SESSION_ID = retry_ids[0]
                return GLOBAL_SESSION_ID
        raise e


# ── XML Builders ──────────────────────────────────────────────────────────────

def build_msg(msg_type, body_xml, message_id=None):
    m_id = message_id or str(uuid.uuid4())
    source = "crm"
    if msg_type in ("new_registration", "profile_update", "cancel_registration"):
        source = "crm"
    elif msg_type == "badge_scanned":
        source = "iot_gateway"

    if msg_type == "new_registration":
        header = (
            f"<message_id>{m_id}</message_id>"
            "<timestamp>2026-03-31T10:00:00Z</timestamp>"
            f"<source>{source}</source>"
            f"<type>{msg_type}</type>"
            "<version>2.0</version>"
        )
    else:
        header = (
            f"<message_id>{m_id}</message_id>"
            "<timestamp>2026-03-31T10:00:00Z</timestamp>"
            f"<source>{source}</source>"
            f"<type>{msg_type}</type>"
            "<version>2.0</version>"
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>{header}</header>
  <body>{body_xml}</body>
</message>"""


# ── TEST CATEGORY: RECEIVER (Inbound) ──────────────────────────────────────────

def test_registration_and_idempotency():
    section("TEST 1 & 2: new_registration & Idempotency")
    msg_id = str(uuid.uuid4())
    # new_registration XSD: customer plus sibling payment_due in body.
    xml = f"""
    <customer>
      <identity_uuid>{TEST_USER_ID}</identity_uuid>
      <email>test@{TEST_ID}.be</email>
      <date_of_birth>1990-01-01</date_of_birth>
      <contact>
        <first_name>Test</first_name>
        <last_name>User</last_name>
      </contact>
      <session_id>sess-001</session_id>
    </customer>
    <payment_due>
      <amount currency="eur">10.00</amount>
      <status>unpaid</status>
    </payment_due>
    """
    full_xml = build_msg("new_registration", xml, message_id=msg_id)

    # Send first time
    publish(full_xml, "kassa.incoming.registration")
    wait(10, "receiver processing creation")

    uid, models = get_rpc()
    partners = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "res.partner", "search_read",
        [[["x_user_id", "=", TEST_USER_ID]]], {"fields": ["id", "name"]}
    )

    ok1 = len(partners) == 1
    report_result("Receiver: new_registration create", ok1, f"Found {len(partners)} partners")

    # Send second time (same message_id)
    publish(full_xml, "kassa.incoming.registration")
    wait(2, "receiver processing duplicate")

    partners_after = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "res.partner", "search",
        [[["x_user_id", "=", TEST_USER_ID]]]
    )
    ok2 = len(partners_after) == 1
    report_result("Receiver: Idempotency check", ok2, f"Still {len(partners_after)} partners")


def test_profile_update():
    section("TEST 3: profile_update")
    new_email = f"updated-{TEST_ID}@test.be"
    # profile_update XSD: identity_uuid, email, dob, contact, type, company_name, vat_number, company_id, payment_due
    xml = f"""
      <identity_uuid>{TEST_USER_ID}</identity_uuid>
      <email>{new_email}</email>
      <date_of_birth>1990-01-01</date_of_birth>
      <contact>
        <first_name>Test</first_name>
        <last_name>Updated</last_name>
      </contact>
      <type>private</type>
    """
    publish(build_msg("profile_update", xml), "kassa.incoming.profile")
    wait(10, "receiver processing update")

    uid, models = get_rpc()
    partner_list = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "res.partner", "search_read",
        [[["x_user_id", "=", TEST_USER_ID]]], {"fields": ["email", "name"]}
    )

    if not partner_list:
        msg = "Partner not found in Odoo after update"
        report_result("Receiver: profile_update", False, msg)
        return

    partner = partner_list[0]
    ok = partner["email"] == new_email and partner["name"] == "Test Updated"
    report_result(
        "Receiver: profile_update", ok,
        f"Email: {partner['email']}, Name: {partner['name']}"
    )


def test_cancellation():
    section("TEST 4: cancel_registration")
    xml = f"<identity_uuid>{TEST_USER_ID}</identity_uuid><session_id>s1</session_id><reason>Testing</reason>"
    publish(build_msg("cancel_registration", xml), "kassa.incoming.cancel")
    wait(8, "receiver processing cancellation")

    uid, models = get_rpc()
    # Fix E501: wrap the long line
    domain = [
        ["x_user_id", "=", TEST_USER_ID],
        ["active", "in", [True, False]]
    ]
    partner_results = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "res.partner", "search_read",
        [domain], {"fields": ["active"]}
    )

    if not partner_results:
        report_result("Receiver: cancel_registration", False, "Partner not found in Odoo")
        return

    partner = partner_results[0]
    ok = partner["active"] is False
    report_result("Receiver: cancel_registration (soft delete)", ok, f"Active: {partner['active']}")

    # Reactivate for further tests
    models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "res.partner",
        "write", [[partner["id"]], {"active": True}]
    )


# ── TEST CATEGORY: SENDER (Outbound) ──────────────────────────────────────────

def test_pos_order_sync():
    section("TEST 5: POS Order Synchronization (Odoo -> RabbitMQ)")
    uid, models = get_rpc()

    # 1. Ensure opened session
    session_id = ensure_opened_session(uid, models)

    # 2. Setup minimal order
    partner_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "res.partner", "search",
        [[["x_user_id", "=", TEST_USER_ID]]]
    )
    partner_id = partner_ids[0]
    product_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "product.product", "search",
        [[["available_in_pos", "=", True]]], {"limit": 1}
    )
    product_id = product_ids[0]

    order_id = models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.order", "create", [{
        "session_id": session_id, "partner_id": partner_id,
        "amount_total": 15.0, "amount_paid": 15.0, "amount_tax": 0.0, "amount_return": 0.0,
    }])
    models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.order.line", "create", [{
        "order_id": order_id, "product_id": product_id, "qty": 1, "price_unit": 15.0,
        "price_subtotal": 15.0, "price_subtotal_incl": 15.0,
    }])

    print(f"  [ODOO] Created Order ID: {order_id}")

    # 3. Mark as paid to trigger poller
    models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "pos.order",
        "write", [[order_id], {"state": "paid"}]
    )

    # 4. Wait for poller (interval is 3-5s)
    wait(12, "order poller to pick up order")

    # 5. Check if x_rabbitmq_sent flag was updated
    order = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "pos.order",
        "read", [order_id, ["x_rabbitmq_sent", "x_rabbitmq_error"]]
    )[0]

    ok = order["x_rabbitmq_sent"] is True
    report_result(
        "Sender: POS Order Polling", ok,
        f"x_rabbitmq_sent = {order['x_rabbitmq_sent']}, error = {order.get('x_rabbitmq_error')}"
    )


def test_refund_flow():
    section("TEST 8: Refund Flow (Negative Order)")
    uid, models = get_rpc()
    session_id = ensure_opened_session(uid, models)

    partner_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "res.partner", "search",
        [[["x_user_id", "=", TEST_USER_ID]]]
    )
    partner_id = partner_ids[0]
    product_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "product.product", "search",
        [[["available_in_pos", "=", True]]], {"limit": 1}
    )
    product_id = product_ids[0]

    # Create NEGATIVE order
    order_id = models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.order", "create", [{
        "session_id": session_id, "partner_id": partner_id,
        "amount_total": -10.0, "amount_paid": -10.0, "amount_tax": 0.0, "amount_return": 0.0,
    }])
    models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.order.line", "create", [{
        "order_id": order_id, "product_id": product_id, "qty": -1, "price_unit": 10.0,
        "price_subtotal": -10.0, "price_subtotal_incl": -10.0,
    }])

    models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.order", "write", [[order_id], {"state": "paid"}])
    print(f"  [ODOO] Created Refund ID: {order_id}")

    wait(12, "order poller to pick up refund")

    order = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "pos.order", "read", [order_id, ["x_rabbitmq_sent"]]
    )[0]
    ok = order["x_rabbitmq_sent"] is True
    report_result("Sender: Refund Processing", ok, f"x_rabbitmq_sent = {order['x_rabbitmq_sent']}")


def test_invoice_flow():
    section("TEST 9: Invoice Request Flow")
    uid, models = get_rpc()
    session_id = ensure_opened_session(uid, models)

    partner_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "res.partner", "search",
        [[["x_user_id", "=", TEST_USER_ID]]]
    )
    partner_id = partner_ids[0]
    product_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "product.product", "search",
        [[["available_in_pos", "=", True]]], {"limit": 1}
    )
    product_id = product_ids[0]

    # Create order with to_invoice=True
    order_id = models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.order", "create", [{
        "session_id": session_id, "partner_id": partner_id, "to_invoice": True,
        "amount_total": 20.0, "amount_paid": 20.0, "amount_tax": 0.0, "amount_return": 0.0,
    }])
    models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.order.line", "create", [{
        "order_id": order_id, "product_id": product_id, "qty": 1, "price_unit": 20.0,
        "price_subtotal": 20.0, "price_subtotal_incl": 20.0,
    }])

    models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.order", "write", [[order_id], {"state": "paid"}])
    print(f"  [ODOO] Created Invoice Order ID: {order_id}")

    wait(12, "order poller to pick up invoice request")

    order = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "pos.order", "read", [order_id, ["x_rabbitmq_sent"]]
    )[0]
    ok = order["x_rabbitmq_sent"] is True
    report_result("Sender: Invoice Request", ok, f"x_rabbitmq_sent = {order['x_rabbitmq_sent']}")


def test_wallet_payment_flow():
    section("TEST 10: Wallet Payment Flow")
    uid, models = get_rpc()
    session_id = ensure_opened_session(uid, models)

    # Find Badge Wallet payment method
    pm_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "pos.payment.method", "search",
        [[["name", "ilike", "Badge Wallet"]]]
    )
    if not pm_ids:
        # Fallback to any PM if Badge Wallet is missing in this environment
        pm_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.payment.method", "search", [[]])

    pm_id = pm_ids[0]
    partner_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "res.partner", "search",
        [[["x_user_id", "=", TEST_USER_ID]]]
    )
    partner_id = partner_ids[0]
    product_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "product.product", "search",
        [[["available_in_pos", "=", True]]], {"limit": 1}
    )
    product_id = product_ids[0]

    # Create order
    order_id = models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.order", "create", [{
        "session_id": session_id, "partner_id": partner_id,
        "amount_total": 5.0, "amount_paid": 5.0, "amount_tax": 0.0, "amount_return": 0.0,
    }])
    models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.order.line", "create", [{
        "order_id": order_id, "product_id": product_id, "qty": 1, "price_unit": 5.0,
        "price_subtotal": 5.0, "price_subtotal_incl": 5.0,
    }])

    # Add payment via Wallet
    models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.payment", "create", [{
        "pos_order_id": order_id, "payment_method_id": pm_id, "amount": 5.0,
    }])

    models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.order", "write", [[order_id], {"state": "paid"}])
    print(f"  [ODOO] Created Wallet Order ID: {order_id}")

    wait(12, "order poller to pick up wallet payment")

    order = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "pos.order", "read", [order_id, ["x_rabbitmq_sent"]]
    )[0]
    ok = order["x_rabbitmq_sent"] is True
    report_result("Sender: Wallet Payment Update", ok, f"x_rabbitmq_sent = {order['x_rabbitmq_sent']}")


def test_anonymous_order_flow():
    section("TEST 11: Anonymous Order Flow")
    uid, models = get_rpc()
    session_id = ensure_opened_session(uid, models)

    product_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "product.product", "search",
        [[["available_in_pos", "=", True]]], {"limit": 1}
    )
    product_id = product_ids[0]

    # Create order WITHOUT partner_id
    order_id = models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.order", "create", [{
        "session_id": session_id, "partner_id": False,
        "amount_total": 7.5, "amount_paid": 7.5, "amount_tax": 0.0, "amount_return": 0.0,
    }])
    models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.order.line", "create", [{
        "order_id": order_id, "product_id": product_id, "qty": 1, "price_unit": 7.5,
        "price_subtotal": 7.5, "price_subtotal_incl": 7.5,
    }])

    models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.order", "write", [[order_id], {"state": "paid"}])
    print(f"  [ODOO] Created Anonymous Order ID: {order_id}")

    wait(12, "order poller to pick up anonymous order")

    order = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "pos.order", "read", [order_id, ["x_rabbitmq_sent"]]
    )[0]
    ok = order["x_rabbitmq_sent"] is True
    report_result("Sender: Anonymous Order", ok, f"x_rabbitmq_sent = {order['x_rabbitmq_sent']}")


# ── TEST CATEGORY: SYSTEM (Validation & Resilience) ──────────────────────────

def test_xsd_rejection():
    section("TEST 6: XSD Validation Enforcement")
    # Missing required <contact> block
    broken_xml = f"""
    <customer>
      <identity_uuid>broken-{TEST_ID}</identity_uuid>
      <type>private</type>
    </customer>
    """
    publish(build_msg("new_registration", broken_xml), "kassa.incoming.registration")
    wait(4, "receiver processing invalid XML")

    uid, models = get_rpc()
    count = len(models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "res.partner", "search",
        [[["x_user_id", "=", f"broken-{TEST_ID}"]]]
    ))

    ok = count == 0
    report_result("System: XSD Rejection", ok, "Invalid XML was correctly blocked")


def test_monitoring_log():
    section("TEST 7: Monitoring Log (Direct to Default Exchange)")
    # Since we can't easily "listen" to the default exchange 'logs' queue without
    # setting up a new consumer in this script, we'll verify the sender doesn't crash
    # and that it correctly handles the logic.

    # In a real environment, we'd check if the message arrived in the 'logs' queue.
    # For this suite, we trigger a flow that we know generates a log (like an XSD rejection)
    # and verify the system remains stable.

    from monitoring import monitor
    try:
        monitor.log("info", "session", "Integration test suite started")
        ok = True
        reason = "Monitor log triggered successfully without exceptions"
    except Exception as e:
        ok = False
        reason = f"Monitor log failed: {e}"

    report_result("System: Monitoring Integration", ok, reason)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*70}\n  KASSA COMPREHENSIVE INTEGRATION TEST SUITE\n{'='*70}")
    print(f"  Target Odoo     : {ODOO_URL} ({ODOO_DB})")
    print(f"  Target RabbitMQ : {RABBIT_HOST}:{RABBIT_PORT}")

    try:
        test_registration_and_idempotency()
        test_profile_update()
        test_cancellation()
        test_pos_order_sync()
        test_refund_flow()
        test_invoice_flow()
        test_wallet_payment_flow()
        test_anonymous_order_flow()
        test_xsd_rejection()
        test_monitoring_log()

        section("SUMMARY")
        all_pass = True
        for name, res, reason in RESULTS:
            print(f"  {'✅' if res == 'PASS' else '❌'} {res.ljust(5)} | {name.ljust(35)} | {reason}")
            if res != "PASS":
                all_pass = False

        print(f"\n  Final Result: {'ALL PASS ✅' if all_pass else 'FAILURES DETECTED ❌'}")
        sys.exit(0 if all_pass else 1)

    except Exception as e:
        print(f"\n❌ CRITICAL TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
