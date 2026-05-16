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
TEST_USER_ID = str(uuid.uuid4())
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

def build_msg(msg_type, body_xml, message_id=None, correlation_id=None):
    m_id = message_id or str(uuid.uuid4())
    corr_id = correlation_id or str(uuid.uuid4())

    source_map = {
        "badge_scanned": "iot_gateway",
        "event_ended":   "frontend",
    }
    source = source_map.get(msg_type, "crm")

    header_parts = [
        f"<message_id>{m_id}</message_id>",
        "<timestamp>2026-03-31T10:00:00Z</timestamp>",
        f"<source>{source}</source>",
        f"<type>{msg_type}</type>",
        "<version>2.0</version>"
    ]

    # Types that REQUIRE correlation_id per their XSD
    require_corr_id = {"new_registration", "wallet_lease_grant", "wallet_remote_topup"}
    # Types that MUST NOT include correlation_id per their XSD
    forbid_corr_id = {"badge_scanned"}

    if msg_type in require_corr_id:
        header_parts.append(f"<correlation_id>{corr_id}</correlation_id>")
    elif msg_type not in forbid_corr_id and correlation_id:
        header_parts.append(f"<correlation_id>{correlation_id}</correlation_id>")

    header = "".join(header_parts)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>{header}</header>
  <body>{body_xml}</body>
</message>"""


# ── TEST CATEGORY: RECEIVER (Inbound) ──────────────────────────────────────────

def test_registration_and_idempotency():
    section("TEST 1 & 2: new_registration & Idempotency")
    msg_id = str(uuid.uuid4())
    # new_registration XSD: payment_due MUST be nested inside customer
    xml = f"""
    <customer>
      <identity_uuid>{TEST_USER_ID}</identity_uuid>
      <email>test@{TEST_ID}.be</email>
      <date_of_birth>1990-01-01</date_of_birth>
      <contact>
        <first_name>Test</first_name>
        <last_name>User</last_name>
      </contact>
      <type>private</type>
      <payment_due>
        <amount currency="eur">10.00</amount>
        <status>unpaid</status>
      </payment_due>
    </customer>
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
    if not partner_ids:
        report_result("Sender: POS Order Polling", False, "Setup failed: Test partner not found")
        return
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
    if not partner_ids:
        report_result("Sender: POS Order Polling", False, "Setup failed: Test partner not found")
        return
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
    section("TEST 9: Private Person Invoice Request Flow")
    uid, models = get_rpc()
    session_id = ensure_opened_session(uid, models)

    partner_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "res.partner", "search",
        [[["x_user_id", "=", TEST_USER_ID]]]
    )
    if not partner_ids:
        report_result("Sender: Invoice Request (private)", False, "Setup failed: Test partner not found")
        return
    partner_id = partner_ids[0]

    # Ensure partner is private (not a company)
    models.execute_kw(ODOO_DB, uid, ODOO_PASS, "res.partner", "write",
                      [[partner_id], {"is_company": False}])

    product_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "product.product", "search",
        [[["available_in_pos", "=", True]]], {"limit": 1}
    )
    product_id = product_ids[0]

    # Private person requests invoice — cashier sets to_invoice=True; pays cash (state stays paid)
    order_id = models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.order", "create", [{
        "session_id": session_id, "partner_id": partner_id, "to_invoice": True,
        "amount_total": 20.0, "amount_paid": 20.0, "amount_tax": 0.0, "amount_return": 0.0,
    }])
    models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.order.line", "create", [{
        "order_id": order_id, "product_id": product_id, "qty": 1, "price_unit": 20.0,
        "price_subtotal": 20.0, "price_subtotal_incl": 20.0,
    }])

    models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.order", "write", [[order_id], {"state": "paid"}])
    print(f"  [ODOO] Created Private Invoice Order ID: {order_id}")

    wait(12, "order poller to pick up private invoice request")

    order = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "pos.order", "read",
        [order_id, ["x_rabbitmq_sent", "x_invoice_message_id"]]
    )[0]
    sent_ok = order["x_rabbitmq_sent"] is True
    invoice_ok = bool(order.get("x_invoice_message_id"))
    report_result(
        "Sender: Invoice Request (private)",
        sent_ok and invoice_ok,
        f"x_rabbitmq_sent={order['x_rabbitmq_sent']}, x_invoice_message_id={'set' if invoice_ok else 'missing'}"
    )


def test_company_customer_account_pending_flow():
    section("TEST 9b: Company Customer Account — Deferred Payment Flow")
    uid, models = get_rpc()
    session_id = ensure_opened_session(uid, models)

    # Find or create a company partner with VAT and x_user_id
    company_user_id = str(uuid.uuid4())
    company_partner_id = models.execute_kw(ODOO_DB, uid, ODOO_PASS, "res.partner", "create", [{
        "name": f"TestCorp-{TEST_ID}",
        "is_company": True,
        "email": f"corp-{TEST_ID}@example.com",
        "vat": "BE0123456789",
        "x_user_id": company_user_id,
        "street": "Zakenlaan 1",
        "city": "Gent",
        "zip": "9000",
    }])
    print(f"  [ODOO] Created company partner ID: {company_partner_id}")

    # Find Customer Account payment method
    ca_pm_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "pos.payment.method", "search",
        [[["name", "ilike", "Customer Account"]]], {"limit": 1}
    )
    if not ca_pm_ids:
        report_result(
            "Sender: Company Customer Account (pending)",
            False,
            "Customer Account payment method not found in Odoo"
        )
        # Cleanup
        models.execute_kw(ODOO_DB, uid, ODOO_PASS, "res.partner", "write",
                          [[company_partner_id], {"active": False}])
        return
    ca_pm_id = ca_pm_ids[0]

    product_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "product.product", "search",
        [[["available_in_pos", "=", True]]], {"limit": 1}
    )
    product_id = product_ids[0]

    # Company order: to_invoice=True + Customer Account (Odoo sets both automatically on validate)
    order_id = models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.order", "create", [{
        "session_id": session_id, "partner_id": company_partner_id, "to_invoice": True,
        "amount_total": 50.0, "amount_paid": 50.0, "amount_tax": 0.0, "amount_return": 0.0,
    }])
    models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.order.line", "create", [{
        "order_id": order_id, "product_id": product_id, "qty": 1, "price_unit": 50.0,
        "price_subtotal": 50.0, "price_subtotal_incl": 50.0,
    }])
    # Attach Customer Account payment
    models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.payment", "create", [{
        "pos_order_id": order_id, "payment_method_id": ca_pm_id, "amount": 50.0,
    }])

    models.execute_kw(ODOO_DB, uid, ODOO_PASS, "pos.order", "write", [[order_id], {"state": "invoiced"}])
    print(f"  [ODOO] Created Company Customer Account Order ID: {order_id}")

    wait(12, "order poller to pick up company customer account order")

    order = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "pos.order", "read",
        [order_id, ["x_rabbitmq_sent", "x_invoice_message_id", "x_payment_message_id"]]
    )[0]
    sent_ok = order["x_rabbitmq_sent"] is True
    invoice_ok = bool(order.get("x_invoice_message_id"))
    payment_ok = bool(order.get("x_payment_message_id"))
    report_result(
        "Sender: Company Customer Account (pending)",
        sent_ok and invoice_ok and payment_ok,
        f"sent={order['x_rabbitmq_sent']}, invoice_msg={'set' if invoice_ok else 'missing'}, "
        f"payment_msg={'set' if payment_ok else 'missing'}"
    )

    # Cleanup
    models.execute_kw(ODOO_DB, uid, ODOO_PASS, "res.partner", "write",
                      [[company_partner_id], {"active": False}])


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
    if not partner_ids:
        report_result("Sender: POS Order Polling", False, "Setup failed: Test partner not found")
        return
    partner_id = partner_ids[0]

    # Ensure partner has sufficient wallet balance and an active confirmed lease for this test.
    models.execute_kw(ODOO_DB, uid, ODOO_PASS, "res.partner", "write", [
        [partner_id],
        {"x_wallet_balance": 50.0, "x_lease_active": True, "x_lease_id": "test-lease-wallet-10"},
    ])

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


# ── TEST CATEGORY: AUTHORITY LEASE MODEL ─────────────────────────────────────

def test_lease_grant():
    """CRM grants Kassa wallet authority — balance and lease_id must be written to Odoo."""
    section("TEST 12: Wallet Lease Grant")
    uid, models = get_rpc()

    partner_list = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "res.partner", "search_read",
        [[["x_user_id", "=", TEST_USER_ID]]],
        {"fields": ["id", "x_lease_active"], "limit": 1},
    )
    if not partner_list:
        report_result("Lease: wallet_lease_grant", False, "Test partner not found — run registration first")
        return

    partner_id = partner_list[0]["id"]
    lease_id = f"LEASE-{TEST_ID}"

    # Direct Odoo write to prepare the expected pre-state (lease requested, not yet granted)
    models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "res.partner", "write",
        [[partner_id], {"x_lease_active": True, "x_lease_id": "", "x_lease_transaction_count": 0}],
    )

    xml = (
        f"<identity_uuid>{TEST_USER_ID}</identity_uuid>"
        f'<current_balance currency="eur">75.00</current_balance>'
        f"<lease_id>{lease_id}</lease_id>"
    )
    publish(build_msg("wallet_lease_grant", xml), "kassa.incoming.lease")
    wait(10, "receiver processing wallet_lease_grant")

    result = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "res.partner", "search_read",
        [[["x_user_id", "=", TEST_USER_ID]]],
        {"fields": ["x_wallet_balance", "x_lease_id", "x_lease_active"], "limit": 1},
    )
    if not result:
        report_result("Lease: wallet_lease_grant", False, "Partner not found after grant")
        return

    p = result[0]
    ok = p["x_wallet_balance"] == 75.0 and p["x_lease_id"] == lease_id and p["x_lease_active"] is True
    report_result(
        "Lease: wallet_lease_grant", ok,
        f"balance={p['x_wallet_balance']}, lease_id={p['x_lease_id']}, active={p['x_lease_active']}"
    )


def test_lease_remote_topup():
    """CRM pushes a remote top-up during an active lease — balance must increase atomically."""
    section("TEST 13: Remote Wallet Top-up")
    uid, models = get_rpc()

    result = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "res.partner", "search_read",
        [[["x_user_id", "=", TEST_USER_ID]]],
        {"fields": ["id", "x_wallet_balance", "x_lease_active"], "limit": 1},
    )
    if not result:
        report_result("Lease: wallet_remote_topup", False, "Test partner not found")
        return

    p = result[0]
    if not p["x_lease_active"]:
        report_result("Lease: wallet_remote_topup", False, "Prerequisite: no active lease (run test_lease_grant first)")
        return

    initial_balance = float(p["x_wallet_balance"] or 0.0)

    xml = (
        f"<identity_uuid>{TEST_USER_ID}</identity_uuid>"
        f'<add_amount currency="eur">20.00</add_amount>'
        "<reason>festival top-up</reason>"
    )
    publish(build_msg("wallet_remote_topup", xml), "kassa.incoming.lease")
    wait(10, "receiver processing wallet_remote_topup")

    after = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "res.partner", "search_read",
        [[["x_user_id", "=", TEST_USER_ID]]],
        {"fields": ["x_wallet_balance"], "limit": 1},
    )
    if not after:
        report_result("Lease: wallet_remote_topup", False, "Partner not found after topup")
        return

    new_balance = float(after[0]["x_wallet_balance"] or 0.0)
    expected = round(initial_balance + 20.0, 2)
    ok = abs(new_balance - expected) < 0.01
    report_result(
        "Lease: wallet_remote_topup", ok,
        f"balance: {initial_balance:.2f} + 20.00 → {new_balance:.2f} (expected {expected:.2f})"
    )


def test_session_created_creates_pos_product():
    """Integration: session_created message (Frontend→Kassa) → POS product created in Odoo."""
    section("TEST 15: session_created Creates POS Product")
    uid, models = get_rpc()

    session_title = f"Integration Test Session {TEST_ID}"

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>{str(uuid.uuid4())}</message_id>
    <timestamp>2026-05-13T09:00:00Z</timestamp>
    <source>frontend</source>
    <type>session_created</type>
    <version>2.0</version>
  </header>
  <body>
    <session_id>integ-sess-{TEST_ID}</session_id>
    <title>{session_title}</title>
    <start_datetime>2026-06-01T09:00:00</start_datetime>
    <end_datetime>2026-06-01T11:00:00</end_datetime>
    <price currency="eur">35.00</price>
  </body>
</message>"""

    publish(xml, "kassa.incoming")
    wait(8, "receiver processing session_created")

    products = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "product.template", "search_read",
        [[["name", "=", session_title], ["available_in_pos", "=", True]]],
        {"fields": ["name", "list_price", "type"]},
    )
    ok = len(products) == 1
    price_ok = ok and abs(products[0]["list_price"] - 35.0) < 0.01
    report_result(
        "session_created: product created",
        ok and price_ok,
        f"found={len(products)}, price={products[0]['list_price'] if products else 'n/a'}",
    )

    # Cleanup
    if products:
        pt_ids = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS, "product.template", "search",
            [[["name", "=", session_title]]],
        )
        if pt_ids:
            models.execute_kw(ODOO_DB, uid, ODOO_PASS, "product.template", "write",
                              [pt_ids, {"active": False}])


def test_user_sessions_response_creates_pos_product():
    """Integration: user_sessions_response → POS product created for the user's session."""
    section("TEST 16: user_sessions_response Creates POS Product")
    uid, models = get_rpc()

    session_title = f"QR Session {TEST_ID}"
    correlation_id = str(uuid.uuid4())
    identity_uuid = str(uuid.uuid4())

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>{str(uuid.uuid4())}</message_id>
    <timestamp>2026-05-13T09:00:00Z</timestamp>
    <source>frontend</source>
    <type>user_sessions_response</type>
    <version>2.0</version>
    <correlation_id>{correlation_id}</correlation_id>
  </header>
  <body>
    <identity_uuid>{identity_uuid}</identity_uuid>
    <status>ok</status>
    <session_count>1</session_count>
    <sessions>
      <session>
        <session_id>qr-sess-{TEST_ID}</session_id>
        <title>{session_title}</title>
        <start_datetime>2026-06-01T13:00:00Z</start_datetime>
        <end_datetime>2026-06-01T14:00:00Z</end_datetime>
        <location>Room C</location>
        <session_type>keynote</session_type>
        <status>published</status>
        <max_attendees>200</max_attendees>
        <current_attendees>10</current_attendees>
        <price currency="eur">20.00</price>
      </session>
    </sessions>
  </body>
</message>"""

    publish(xml, "kassa.incoming")
    wait(8, "receiver processing user_sessions_response")

    products = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "product.template", "search_read",
        [[["name", "=", session_title], ["available_in_pos", "=", True]]],
        {"fields": ["name", "list_price"]},
    )
    ok = len(products) == 1
    price_ok = ok and abs(products[0]["list_price"] - 20.0) < 0.01
    report_result(
        "user_sessions_response: product created",
        ok and price_ok,
        f"found={len(products)}, price={products[0]['list_price'] if products else 'n/a'}",
    )

    # Cleanup — archive instead of delete: open POS sessions block product deletion
    if products:
        pt_ids = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS, "product.template", "search",
            [[["name", "=", session_title]]],
        )
        if pt_ids:
            models.execute_kw(ODOO_DB, uid, ODOO_PASS, "product.template", "write",
                              [pt_ids, {"active": False}])


def test_kassa_notify_product_update_callable():
    """Integration: kassa_notify_product_update on pos.session is callable via XML-RPC.

    Verifies the custom addon method is installed and returns the number of
    notified sessions (integer) without raising.
    """
    section("TEST 17: kassa_notify_product_update Callable via XML-RPC")
    uid, models = get_rpc()

    try:
        result = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "pos.session", "kassa_notify_product_update", [[]],
        )
        ok = isinstance(result, int)
        report_result(
            "kassa_notify_product_update callable",
            ok,
            f"returned {result!r} (expected int)",
        )
    except Exception as e:
        report_result(
            "kassa_notify_product_update callable",
            False,
            f"exception: {e}",
        )


def test_session_product_in_sessions_category():
    """Integration: product created by session_created is in the 'Sessions' POS category."""
    section("TEST 18: Session Product Has Correct POS Category")
    uid, models = get_rpc()

    session_title = f"Category Test Session {TEST_ID}"

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>{str(uuid.uuid4())}</message_id>
    <timestamp>2026-05-13T09:00:00Z</timestamp>
    <source>frontend</source>
    <type>session_created</type>
    <version>2.0</version>
  </header>
  <body>
    <session_id>cat-sess-{TEST_ID}</session_id>
    <title>{session_title}</title>
    <start_datetime>2026-06-01T09:00:00</start_datetime>
    <end_datetime>2026-06-01T11:00:00</end_datetime>
  </body>
</message>"""

    publish(xml, "kassa.incoming")
    wait(8, "receiver processing session_created for category test")

    sessions_categ = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "pos.category", "search_read",
        [[["name", "=", "Sessions"]]], {"fields": ["id"]},
    )
    if not sessions_categ:
        report_result("session product category", False, "'Sessions' POS category not found in Odoo")
        return

    categ_id = sessions_categ[0]["id"]
    products = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "product.template", "search_read",
        [[["name", "=", session_title], ["available_in_pos", "=", True]]],
        {"fields": ["pos_categ_ids"]},
    )

    ok = len(products) == 1 and categ_id in (products[0].get("pos_categ_ids") or [])
    report_result(
        "session product category",
        ok,
        f"found={len(products)}, categ_ids={products[0]['pos_categ_ids'] if products else 'n/a'}",
    )

    # Cleanup — archive instead of delete: open POS sessions block product deletion
    if products:
        pt_ids = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS, "product.template", "search",
            [[["name", "=", session_title]]],
        )
        if pt_ids:
            models.execute_kw(ODOO_DB, uid, ODOO_PASS, "product.template", "write",
                              [pt_ids, {"active": False}])


def test_lease_topup_rejected_without_active_lease():
    """Remote top-up must be silently rejected when no active lease exists."""
    section("TEST 14: Remote Top-up Rejected (no active lease)")
    uid, models = get_rpc()

    result = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "res.partner", "search_read",
        [[["x_user_id", "=", TEST_USER_ID]]],
        {"fields": ["id", "x_wallet_balance"], "limit": 1},
    )
    if not result:
        report_result("Lease: topup_rejected_no_lease", False, "Test partner not found")
        return

    partner_id = result[0]["id"]
    balance_before = float(result[0]["x_wallet_balance"] or 0.0)

    # Explicitly clear the lease so the topup must be rejected
    models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "res.partner", "write",
        [[partner_id], {"x_lease_active": False, "x_lease_id": "", "x_lease_transaction_count": 0}],
    )

    xml = (
        f"<identity_uuid>{TEST_USER_ID}</identity_uuid>"
        f'<add_amount currency="eur">50.00</add_amount>'
        "<reason>should be rejected</reason>"
    )
    publish(build_msg("wallet_remote_topup", xml), "kassa.incoming.lease")
    wait(10, "receiver processing rejected topup")

    after = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "res.partner", "search_read",
        [[["x_user_id", "=", TEST_USER_ID]]],
        {"fields": ["x_wallet_balance"], "limit": 1},
    )
    balance_after = float(after[0]["x_wallet_balance"] or 0.0) if after else balance_before
    ok = abs(balance_after - balance_before) < 0.01
    report_result(
        "Lease: topup_rejected_no_lease", ok,
        f"balance unchanged at {balance_after:.2f} (rejected top-up of 50.00)"
    )


# ── TEST CATEGORY: BADGE SCAN ─────────────────────────────────────────────────

def test_badge_scanned_entrance_triggers_lease():
    """badge_scanned at 'entrance' must set x_lease_active=True on the partner."""
    section("TEST 19: badge_scanned (entrance) → lease requested")
    uid, models = get_rpc()

    badge_id = f"INTEG-BADGE-{TEST_ID.upper()}"
    identity_uuid = str(uuid.uuid4())
    partner_id = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "res.partner", "create",
        [{"name": f"Badge Test Partner {TEST_ID}", "x_user_id": identity_uuid,
          "x_badge_id": badge_id}],
    )

    xml = build_msg(
        "badge_scanned",
        f"<badge_id>{badge_id}</badge_id>"
        f"<location>entrance</location>"
        f"<scanned_at>2026-06-01T09:00:00</scanned_at>",
    )
    publish(xml, "kassa.incoming.badge")
    wait(10, "receiver processing badge_scanned at entrance")

    result = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "res.partner", "search_read",
        [[["id", "=", partner_id]]],
        {"fields": ["x_lease_active"], "limit": 1},
    )
    lease_active = result[0]["x_lease_active"] if result else False
    report_result(
        "Badge: entrance scan triggers lease",
        lease_active is True,
        f"x_lease_active={lease_active}",
    )

    # Cleanup
    models.execute_kw(ODOO_DB, uid, ODOO_PASS, "res.partner", "write",
                      [[partner_id], {"active": False, "x_lease_active": False}])


def test_badge_scanned_unknown_badge_graceful():
    """badge_scanned with an unrecognised badge_id must not crash — system stays responsive."""
    section("TEST 20: badge_scanned (unknown badge) → graceful no-op")
    uid, models = get_rpc()

    random_badge = f"GHOST-{uuid.uuid4().hex[:12].upper()}"
    xml = build_msg(
        "badge_scanned",
        f"<badge_id>{random_badge}</badge_id>"
        f"<location>entrance</location>"
        f"<scanned_at>2026-06-01T09:00:00</scanned_at>",
    )
    publish(xml, "kassa.incoming.badge")
    wait(6, "receiver processing unknown badge")

    # System is still up if we can still read from Odoo
    try:
        models.execute_kw(ODOO_DB, uid, ODOO_PASS, "res.partner", "search", [[["id", "=", 1]]])
        ok = True
        reason = f"System responsive after unknown badge {random_badge}"
    except Exception as exc:
        ok = False
        reason = f"System unresponsive: {exc}"

    report_result("Badge: unknown badge graceful", ok, reason)


# ── TEST CATEGORY: SESSION LIFECYCLE ──────────────────────────────────────────

def test_session_updated_changes_pos_product_price():
    """session_updated must update the matching POS product's list_price."""
    section("TEST 21: session_updated → POS product price updated")
    uid, models = get_rpc()

    session_title = f"Update Test Session {TEST_ID}"
    session_id = f"upd-sess-{TEST_ID}"

    # First create the product via session_created
    create_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>{str(uuid.uuid4())}</message_id>
    <timestamp>2026-05-13T09:00:00Z</timestamp>
    <source>frontend</source>
    <type>session_created</type>
    <version>2.0</version>
  </header>
  <body>
    <session_id>{session_id}</session_id>
    <title>{session_title}</title>
    <start_datetime>2026-06-01T09:00:00</start_datetime>
    <end_datetime>2026-06-01T11:00:00</end_datetime>
    <price currency="eur">40.00</price>
  </body>
</message>"""
    publish(create_xml, "kassa.incoming")
    wait(8, "receiver processing session_created for update test")

    # Now send session_updated with a changed price
    update_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>{str(uuid.uuid4())}</message_id>
    <timestamp>2026-05-13T10:00:00Z</timestamp>
    <source>frontend</source>
    <type>session_updated</type>
    <version>2.0</version>
  </header>
  <body>
    <session_id>{session_id}</session_id>
    <title>{session_title}</title>
    <start_datetime>2026-06-01T09:00:00</start_datetime>
    <end_datetime>2026-06-01T11:00:00</end_datetime>
    <price currency="eur">25.00</price>
  </body>
</message>"""
    publish(update_xml, "kassa.incoming")
    wait(8, "receiver processing session_updated")

    products = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "product.template", "search_read",
        [[["name", "=", session_title], ["available_in_pos", "=", True]]],
        {"fields": ["name", "list_price"]},
    )
    found = len(products) == 1
    price_updated = found and abs(products[0]["list_price"] - 25.0) < 0.01
    report_result(
        "Session: updated price reflected in POS",
        price_updated,
        f"found={len(products)}, price={products[0]['list_price'] if products else 'n/a'}",
    )

    # Cleanup
    if products:
        pt_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASS, "product.template", "search",
                                   [[["name", "=", session_title]]])
        if pt_ids:
            models.execute_kw(ODOO_DB, uid, ODOO_PASS, "product.template", "write",
                              [pt_ids, {"active": False}])


def test_session_deleted_preserves_pos_product():
    """session_deleted must NOT remove the matching POS product — Kassa intentionally keeps it."""
    section("TEST 22: session_deleted → POS product preserved")
    uid, models = get_rpc()

    session_title = f"Delete Test Session {TEST_ID}"
    session_id = f"del-sess-{TEST_ID}"

    # Create the product first
    create_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>{str(uuid.uuid4())}</message_id>
    <timestamp>2026-05-13T09:00:00Z</timestamp>
    <source>frontend</source>
    <type>session_created</type>
    <version>2.0</version>
  </header>
  <body>
    <session_id>{session_id}</session_id>
    <title>{session_title}</title>
    <start_datetime>2026-06-01T09:00:00</start_datetime>
    <end_datetime>2026-06-01T11:00:00</end_datetime>
    <price currency="eur">15.00</price>
  </body>
</message>"""
    publish(create_xml, "kassa.incoming")
    wait(8, "receiver creating product for delete test")

    delete_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>{str(uuid.uuid4())}</message_id>
    <timestamp>2026-05-13T11:00:00Z</timestamp>
    <source>frontend</source>
    <type>session_deleted</type>
    <version>2.0</version>
  </header>
  <body>
    <session_id>{session_id}</session_id>
    <reason>cancelled by organiser</reason>
  </body>
</message>"""
    publish(delete_xml, "kassa.incoming")
    wait(6, "receiver processing session_deleted")

    products = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "product.template", "search_read",
        [[["name", "=", session_title], ["available_in_pos", "=", True]]],
        {"fields": ["name"]},
    )
    ok = len(products) == 1
    report_result(
        "Session: deleted session keeps POS product",
        ok,
        f"found={len(products)} (expected 1 — product must be preserved)",
    )

    # Cleanup
    if products:
        pt_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASS, "product.template", "search",
                                   [[["name", "=", session_title]]])
        if pt_ids:
            models.execute_kw(ODOO_DB, uid, ODOO_PASS, "product.template", "write",
                              [pt_ids, {"active": False}])


# ── TEST CATEGORY: EDGE CASES ─────────────────────────────────────────────────

def test_cancel_unknown_user_graceful():
    """cancel_registration for a UUID that was never registered must be a silent no-op."""
    section("TEST 23: cancel_registration (unknown user) → graceful no-op")
    uid, models = get_rpc()

    ghost_uuid = str(uuid.uuid4())
    xml = (
        f"<identity_uuid>{ghost_uuid}</identity_uuid>"
        f"<session_id>ghost-sess</session_id>"
        f"<reason>never existed</reason>"
    )
    publish(build_msg("cancel_registration", xml), "kassa.incoming.cancel")
    wait(6, "receiver processing cancellation for unknown user")

    # No partner must have been created or touched; system stays responsive
    partners = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "res.partner", "search",
        [[["x_user_id", "=", ghost_uuid]]],
    )
    ok = len(partners) == 0
    report_result(
        "EdgeCase: cancel unknown user no-op",
        ok,
        f"Partners with ghost uuid: {len(partners)} (expected 0)",
    )


def test_new_registration_sets_outstanding_amount():
    """new_registration must write x_outstanding_amount and x_payment_status to the partner."""
    section("TEST 24: new_registration → outstanding_amount written to Odoo")
    uid, models = get_rpc()

    unique_uuid = str(uuid.uuid4())
    xml = f"""
    <customer>
      <identity_uuid>{unique_uuid}</identity_uuid>
      <email>amount-{TEST_ID}@test.be</email>
      <date_of_birth>1995-05-15</date_of_birth>
      <contact>
        <first_name>Amount</first_name>
        <last_name>Test</last_name>
      </contact>
      <type>private</type>
      <payment_due>
        <amount currency="eur">99.50</amount>
        <status>unpaid</status>
      </payment_due>
    </customer>
    """
    publish(build_msg("new_registration", xml), "kassa.incoming.registration")
    wait(10, "receiver processing registration with payment_due")

    result = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS, "res.partner", "search_read",
        [[["x_user_id", "=", unique_uuid]]],
        {"fields": ["x_outstanding_amount", "x_payment_status"], "limit": 1},
    )

    if not result:
        report_result("Receiver: outstanding_amount set", False, "Partner not found")
        return

    partner = result[0]
    amount_ok = abs(float(partner.get("x_outstanding_amount") or 0) - 99.50) < 0.01
    status_ok = partner.get("x_payment_status") == "unpaid"
    report_result(
        "Receiver: outstanding_amount set",
        amount_ok and status_ok,
        f"amount={partner.get('x_outstanding_amount')}, status={partner.get('x_payment_status')}",
    )

    # Cleanup
    if result:
        models.execute_kw(ODOO_DB, uid, ODOO_PASS, "res.partner", "write",
                          [[result[0]["id"]], {"active": False}])


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
        test_company_customer_account_pending_flow()
        test_wallet_payment_flow()
        test_anonymous_order_flow()
        test_xsd_rejection()
        test_monitoring_log()
        test_lease_grant()
        test_lease_remote_topup()
        test_lease_topup_rejected_without_active_lease()
        test_session_created_creates_pos_product()
        test_user_sessions_response_creates_pos_product()
        test_kassa_notify_product_update_callable()
        test_session_product_in_sessions_category()
        test_badge_scanned_entrance_triggers_lease()
        test_badge_scanned_unknown_badge_graceful()
        test_session_updated_changes_pos_product_price()
        test_session_deleted_preserves_pos_product()
        test_cancel_unknown_user_graceful()
        test_new_registration_sets_outstanding_amount()

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
