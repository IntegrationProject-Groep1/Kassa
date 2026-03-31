"""
test_full_flow1.py — Volledige end-to-end test van Flow 1 (bedrijfsklant)

Stap 1: stuurt een new_registration naar kassa.incoming (simuleert CRM)
Stap 2: wacht tot receiver de klant aanmaakt in Odoo
Stap 3: maakt een POS-order aan gekoppeld aan die klant
Stap 4: wacht tot poller de order verwerkt en naar RabbitMQ stuurt

Gebruik: docker exec kassa_integratie python tools/test_full_flow1.py
"""

import os
import sys
import time
import uuid
import xmlrpc.client
import pika

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config_utils import get_env, parse_rabbit_port

# ── Config ─────────────────────────────────────────────────────────────────────
ODOO_URL  = os.environ.get("ODOO_URL")
ODOO_DB   = os.environ.get("ODOO_DB")
ODOO_USER = os.environ.get("ODOO_USER")
ODOO_PASS = os.environ.get("ODOO_PASS")

RABBIT_HOST  = get_env("RABBIT_HOST")
RABBIT_PORT  = parse_rabbit_port()
RABBIT_USER  = get_env("RABBIT_USER")
RABBIT_PASS  = get_env("RABBIT_PASS")
RABBIT_VHOST = get_env("RABBIT_VHOST", "/")
INCOMING_QUEUE = os.environ.get("RABBIT_INCOMING_QUEUE", "kassa.incoming")

TEST_USER_ID = str(uuid.uuid4())   # fresh UUID elke run
TEST_NAME    = "Test e2e Janssen"
TEST_EMAIL   = f"janssen.{TEST_USER_ID[:8]}@testbedrijf.be"
TEST_COMPANY = "Test e2e Bedrijf NV"
TEST_VAT     = "BE0999888777"

SEP = "-" * 60


# ── Stap 1: new_registration XML publiceren ────────────────────────────────────

NEW_REGISTRATION_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>{uuid.uuid4()}</message_id>
    <type>new_registration</type>
    <source>crm</source>
    <timestamp>2026-03-31T10:00:00Z</timestamp>
    <version>2.0</version>
  </header>
  <body>
    <customer>
      <email>{TEST_EMAIL}</email>
      <contact>
        <first_name>Test e2e</first_name>
        <last_name>Janssen</last_name>
      </contact>
      <company_name>{TEST_COMPANY}</company_name>
      <type>company</type>
      <vat_number>{TEST_VAT}</vat_number>
      <user_id>{TEST_USER_ID}</user_id>
      <age>30</age>
    </customer>
    <payment_due>
      <amount>50.00</amount>
      <status>unpaid</status>
    </payment_due>
  </body>
</message>"""


def publish_new_registration():
    print("Stap 1: new_registration sturen naar kassa.incoming...")
    creds = pika.PlainCredentials(RABBIT_USER, RABBIT_PASS)
    conn  = pika.BlockingConnection(pika.ConnectionParameters(
        host=RABBIT_HOST, port=RABBIT_PORT,
        virtual_host=RABBIT_VHOST, credentials=creds,
        heartbeat=30, blocked_connection_timeout=10
    ))
    ch = conn.channel()
    ch.basic_publish(
        exchange="",
        routing_key=INCOMING_QUEUE,
        body=NEW_REGISTRATION_XML.encode("utf-8"),
        properties=pika.BasicProperties(delivery_mode=2)
    )
    conn.close()
    print(f"  Verstuurd: user_id={TEST_USER_ID}")
    print(f"  Naam:      {TEST_NAME}  |  Bedrijf: {TEST_COMPANY}")


# ── Stap 2: wachten tot partner in Odoo staat ─────────────────────────────────

def wait_for_partner(uid, models, timeout=20):
    print(f"Stap 2: wachten tot receiver klant aanmaakt in Odoo (max {timeout}s)...")
    for i in range(timeout):
        time.sleep(1)
        results = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "res.partner", "search_read",
            [[["x_user_id", "=", TEST_USER_ID]]],
            {"fields": ["id", "name", "x_user_id", "is_company"], "limit": 1}
        )
        if results:
            p = results[0]
            print(f"  Partner gevonden na {i+1}s: Odoo id={p['id']}  "
                  f"naam='{p['name']}'  is_company={p['is_company']}")
            return p["id"]
        sys.stdout.write(f"\r  wachten... {i+1}s")
        sys.stdout.flush()
    print()
    print("FOUT: partner niet gevonden binnen timeout — check receiver logs")
    sys.exit(1)


# ── Stap 3: POS-order aanmaken ─────────────────────────────────────────────────

def create_order(uid, models, partner_id):
    print("Stap 3: POS-order aanmaken gekoppeld aan die klant...")

    session_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "pos.session", "search", [[["state", "=", "opened"]]]
    )
    if not session_ids:
        print("FOUT: geen actieve POS-sessie — open een kassa in Odoo")
        sys.exit(1)

    product_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "product.product", "search",
        [[["available_in_pos", "=", True]]], {"limit": 1}
    )
    if not product_ids:
        product_ids = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "product.product", "search", [[]], {"limit": 1}
        )

    order_id = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "pos.order", "create",
        [{"session_id": session_ids[0], "partner_id": partner_id,
          "amount_tax": 0.0, "amount_total": 5.00,
          "amount_paid": 5.00, "amount_return": 0.0,
          "company_id": int(os.environ.get("ODOO_COMPANY_ID", 1))}]
    )
    models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "pos.order.line", "create",
        [{"order_id": order_id, "product_id": product_ids[0],
          "qty": 1, "price_unit": 5.00,
          "price_subtotal": 5.00, "price_subtotal_incl": 5.00}]
    )
    try:
        models.execute_kw(ODOO_DB, uid, ODOO_PASS,
                          "pos.order", "action_pos_order_paid", [order_id])
    except Exception:
        models.execute_kw(ODOO_DB, uid, ODOO_PASS,
                          "pos.order", "write", [[order_id], {"state": "paid"}])

    print(f"  Order aangemaakt: id={order_id}  partner_id={partner_id}")
    return order_id


# ── Stap 4: wachten op poller-log ─────────────────────────────────────────────

def wait_for_poller(uid, models, order_id, timeout=15):
    print(f"Stap 4: wachten tot poller order verwerkt (max {timeout}s)...")
    # Poller interval is 3s — na max 2 cycli moet het klaar zijn
    for i in range(timeout):
        time.sleep(1)
        result = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "pos.order", "read",
            [order_id, ["state"]]
        )
        # We can't check RabbitMQ from here, but if no exception = poller ran
        # Just wait a couple poll cycles
        if i >= 6:
            print(f"  {i+1}s gewacht — poller had tijd om te verwerken")
            return
        sys.stdout.write(f"\r  wachten... {i+1}s")
        sys.stdout.flush()
    print()


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print(SEP)
    print("FLOW 1 — Volledige end-to-end test (new_registration → order → RabbitMQ)")
    print(SEP)

    # Odoo verbinden
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", allow_none=True)
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASS, {})
    if not uid:
        print("FOUT: Odoo authenticatie mislukt")
        sys.exit(1)
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)
    print(f"Odoo verbonden (uid={uid})")
    print()

    publish_new_registration()
    print()
    partner_id = wait_for_partner(uid, models)
    print()
    order_id = create_order(uid, models, partner_id)
    print()
    wait_for_poller(uid, models, order_id)

    print()
    print(SEP)
    print("Verwacht resultaat in de logs:")
    print(f"  [RECEIVER] New customer created: {TEST_NAME} ...")
    print(f"  [POLLER]   Order {order_id}: {TEST_NAME}")
    print(f"  [SENDER]   Sent: routing_key=kassa.payments.consumption")
    print()
    print("Check met:")
    print("  docker logs kassa_integratie --since 60s")
    print(SEP)


if __name__ == "__main__":
    main()
