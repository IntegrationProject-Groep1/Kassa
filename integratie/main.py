# main.py – Kassa Integration Service entry point
# Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026
#
# Starts all integration components in separate daemon threads:
#   - receiver   → listens on queue.incoming (RabbitMQ)
#   - poller     → polls Odoo for new POS orders  (when available)
#   - heartbeat  → sends periodic heartbeat        (when available)

import logging
import os
import sys
import threading
import time
import xmlrpc.client
import requests

import receiver
import sender
from order_poller import OrderPoller

logging.getLogger("pika").setLevel(logging.WARNING)


def _run_receiver() -> None:
    """Start the RabbitMQ receiver in a thread. Retries on connection failure."""
    retry_delay = 5  # seconds between retries
    while True:
        try:
            receiver.start_listening()
        except Exception as exc:
            print(f"[MAIN] Receiver crashed: {exc} – retrying in {retry_delay}s…", flush=True)
            time.sleep(retry_delay)


def wait_for_odoo(odoo_url, timeout=120):
    """Wait until Odoo web server is responding (before DB exists)"""
    print("⏳ Waiting for Odoo to become available...", flush=True)
    for i in range(timeout // 5):
        try:
            resp = requests.get(f'{odoo_url}/web/database/selector', timeout=5)
            if resp.status_code < 500:
                print("✅ Odoo web server is up", flush=True)
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(5)
    print("⚠️  Odoo did not respond in time — continuing anyway", flush=True)
    return False


def setup_database(odoo_url, odoo_db, odoo_user, odoo_pass, odoo_master_pass):
    """Auto-create the Odoo database if it doesn't exist yet, then wait until accessible."""
    common = xmlrpc.client.ServerProxy(f'{odoo_url}/xmlrpc/2/common', allow_none=True)

    # Fast path: DB already exists and is accessible
    try:
        uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
        if uid:
            print(f"✅ Database '{odoo_db}' already exists and is accessible", flush=True)
            return True
    except Exception:
        pass

    # Attempt to create the database (ignore errors — it may already exist but not yet ready)
    print(f"📦 Creating database '{odoo_db}'...", flush=True)
    try:
        resp = requests.post(
            f'{odoo_url}/web/database/create',
            data={
                'master_pwd': odoo_master_pass,
                'name': odoo_db,
                'login': odoo_user,
                'password': odoo_pass,
                'lang': 'en_US',
                'country_code': 'be',
                'phone': '',
            },
            timeout=120,
            allow_redirects=True
        )
        if resp.status_code in (200, 302):
            print("✅ Database creation request accepted", flush=True)
        else:
            print(f"ℹ️  Database creation returned {resp.status_code} — may already exist, continuing", flush=True)
    except Exception as e:
        print(f"⚠️  Database creation request failed: {e} — will keep waiting", flush=True)

    # Wait up to 10 minutes for the DB to become accessible (fresh Odoo init takes time)
    print(f"⏳ Waiting for database '{odoo_db}' to become accessible (up to 10 min)...", flush=True)
    for attempt in range(120):
        time.sleep(5)
        try:
            uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
            if uid:
                print(f"✅ Database '{odoo_db}' is now accessible (after ~{(attempt + 1) * 5}s)", flush=True)
                return True
        except Exception:
            pass
        if (attempt + 1) % 6 == 0:
            print(f"   ⏳ Still waiting for DB... ({(attempt + 1) * 5}s elapsed)", flush=True)

    print("❌ Database not accessible after 10 minutes", flush=True)
    return False


def ensure_custom_fields(odoo_url, odoo_db, odoo_user, odoo_pass):
    """
    Create custom fields on res.partner and pos.order if they don't exist yet.
    Safe to call on every startup — skips fields that are already present.
    """
    # Each entry: (ttype, label, extra_vals)
    # x_user_id and x_badge_id are btree-indexed — looked up on every incoming message
    FIELDS = {
        "res.partner": {
            "x_user_id":        ("char",  "External User ID",    {"index": "btree"}),
            "x_badge_id":       ("char",  "Badge ID",            {"index": "btree"}),
            "x_wallet_balance": ("float", "Wallet Balance (EUR)", {}),
            "x_date_of_birth":  ("date",  "Date of Birth",        {}),
        },
        "pos.order": {
            "x_rabbitmq_sent": ("boolean", "Sent to RabbitMQ", {}),
        },
        "product.template": {
            "x_is_topup":       ("boolean", "Is Top-up Product",              {}),
            "x_age_restricted": ("boolean", "Is Age Restricted (Alcohol)",    {}),
        },
    }

    print("🔍 Checking custom Odoo fields...", flush=True)
    try:
        common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
        if not uid:
            print("⚠️  Cannot verify custom fields — Odoo auth failed", flush=True)
            return False

        models = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/object", allow_none=True)
        created = 0

        for model_name, fields in FIELDS.items():
            model_rows = models.execute_kw(
                odoo_db, uid, odoo_pass,
                "ir.model", "search_read",
                [[["model", "=", model_name]]],
                {"fields": ["id"], "limit": 1},
            )
            if not model_rows:
                print(f"⚠️  Model '{model_name}' not found — skipping", flush=True)
                continue

            model_id = model_rows[0]["id"]
            existing = {
                r["name"] for r in models.execute_kw(
                    odoo_db, uid, odoo_pass,
                    "ir.model.fields", "search_read",
                    [[["model", "=", model_name], ["name", "in", list(fields)]]],
                    {"fields": ["name"]},
                )
            }

            for fname, (ttype, label, extra) in fields.items():
                if fname in existing:
                    continue
                models.execute_kw(
                    odoo_db, uid, odoo_pass,
                    "ir.model.fields", "create",
                    [{**{"model_id": model_id, "name": fname,
                         "field_description": label, "ttype": ttype, "store": True}, **extra}],
                )
                print(f"   ✅ Created field {model_name}.{fname} ({ttype})", flush=True)
                created += 1

        if created:
            print(f"✅ Custom fields ready — {created} new field(s) created", flush=True)
        else:
            print("✅ Custom fields ready — all fields already present", flush=True)
        return True

    except Exception as e:
        print(f"⚠️  Could not verify/create custom fields: {type(e).__name__}", flush=True)
        return False


def ensure_pos_installed(odoo_url, odoo_db, odoo_user, odoo_pass):
    """
    Check if point_of_sale module is installed in Odoo.
    If not, install it automatically before starting the poller.
    """
    print("🔍 Checking if Point of Sale module is installed...", flush=True)

    try:
        common = xmlrpc.client.ServerProxy(
            f'{odoo_url}/xmlrpc/2/common', allow_none=True)
        uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
        if not uid:
            print("❌ Cannot check modules — Odoo auth failed", flush=True)
            return False

        models = xmlrpc.client.ServerProxy(
            f'{odoo_url}/xmlrpc/2/object', allow_none=True)

        # Find the point_of_sale module record
        module_ids = models.execute_kw(
            odoo_db, uid, odoo_pass,
            'ir.module.module', 'search',
            [[['name', '=', 'point_of_sale']]]
        )

        if not module_ids:
            print("⚠️  point_of_sale module not found in registry", flush=True)
            return False

        module_info = models.execute_kw(
            odoo_db, uid, odoo_pass,
            'ir.module.module', 'read',
            [module_ids, ['name', 'state']]
        )

        state = module_info[0]['state'] if module_info else 'unknown'

        if state == 'installed':
            print("✅ Point of Sale module already installed", flush=True)
            return True

        print(
            f"📦 Point of Sale module state: {state} — installing now...",
            flush=True)

        # Trigger installation
        models.execute_kw(
            odoo_db, uid, odoo_pass,
            'ir.module.module', 'button_immediate_install',
            [module_ids]
        )

        # Wait for installation to complete (up to 120 seconds)
        for attempt in range(24):
            time.sleep(5)
            module_info = models.execute_kw(
                odoo_db, uid, odoo_pass,
                'ir.module.module', 'read',
                [module_ids, ['state']]
            )
            new_state = module_info[0]['state']
            print(
                f"   ⏳ Installing... ({(attempt + 1) * 5}s) state={new_state}",
                flush=True)
            if new_state == 'installed':
                print(
                    "✅ Point of Sale module installed successfully!",
                    flush=True)
                return True

        print("⚠️  POS install timed out — continuing anyway", flush=True)
        return False

    except Exception as e:
        print(f"⚠️  Could not auto-install POS module: {e}", flush=True)
        return False


VALID_VAT_RATES = {0.0, 6.0, 12.0, 21.0}
TARGET_VAT_RATE = 6.0


def ensure_tax_settings(odoo_url, odoo_db, odoo_user, odoo_pass):
    """
    Ensure price-inclusive VAT taxes exist for standard Belgian rates (0%, 6%, 12%, 21%).
    Uses amount_type='division' + price_include_override='tax_included' so list_price IS
    the final customer price. Also fixes POS products with invalid tax rates to 6%.
    Returns a dict mapping {rate: tax_id} for use in ensure_demo_products.
    """
    print("🔍 Checking tax settings and POS product rates...", flush=True)
    try:
        common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
        if not uid:
            print("⚠️  Cannot check tax settings — Odoo auth failed", flush=True)
            return {}

        models = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/object", allow_none=True)

        tax_map_by_rate = {}
        for rate in VALID_VAT_RATES:
            # Always use a 'division' (Percentage Tax Included) tax so list_price IS the final price
            inclusive = models.execute_kw(
                odoo_db, uid, odoo_pass,
                "account.tax", "search_read",
                [[["amount", "=", rate], ["type_tax_use", "in", ["sale", "all"]],
                  ["amount_type", "=", "division"], ["price_include_override", "=", "tax_included"]]],
                {"fields": ["id", "name"], "limit": 1}
            )
            if inclusive:
                tax_id = inclusive[0]["id"]
            else:
                tax_id = models.execute_kw(
                    odoo_db, uid, odoo_pass,
                    "account.tax", "create",
                    [{"name": f"BTW {int(rate)}% incl.", "amount": rate,
                      "type_tax_use": "sale", "amount_type": "division",
                      "price_include_override": "tax_included"}]
                )
                print(f"   ✅ Created {rate}% inclusive tax (division + price_include_override)", flush=True)

            tax_map_by_rate[rate] = tax_id

        target_tax_id = tax_map_by_rate[TARGET_VAT_RATE]

        # Set BTW 6% incl. as the default sales tax on the company
        company_ids = models.execute_kw(odoo_db, uid, odoo_pass, "res.company", "search", [[]])
        if company_ids:
            models.execute_kw(odoo_db, uid, odoo_pass, "res.company", "write",
                              [[company_ids[0]], {"account_sale_tax_id": target_tax_id}])
            print(f"   ✅ Set default sales tax to BTW {TARGET_VAT_RATE}% incl.", flush=True)

        # Check all POS products
        product_ids = models.execute_kw(
            odoo_db, uid, odoo_pass,
            "product.template", "search",
            [[["available_in_pos", "=", True]]]
        )
        if not product_ids:
            return tax_map_by_rate

        products = models.execute_kw(
            odoo_db, uid, odoo_pass,
            "product.template", "read",
            [product_ids, ["id", "name", "taxes_id"]]
        )

        all_tax_ids = list({tid for p in products for tid in p.get("taxes_id", [])})
        tax_map = {}
        if all_tax_ids:
            taxes_data = models.execute_kw(
                odoo_db, uid, odoo_pass,
                "account.tax", "read",
                [all_tax_ids, ["amount"]]
            )
            tax_map = {t["id"]: t["amount"] for t in taxes_data}

        to_fix_ids = []
        for product in products:
            tax_ids = product.get("taxes_id", [])
            if not tax_ids:
                continue  # Tax-free products are intentional — leave them alone
            rates = {float(tax_map.get(tid, -1)) for tid in tax_ids}
            if not rates.issubset(VALID_VAT_RATES):
                print(f"   Fixing '{product['name']}': {rates} → {TARGET_VAT_RATE}%", flush=True)
                to_fix_ids.append(product["id"])

        if to_fix_ids:
            models.execute_kw(
                odoo_db, uid, odoo_pass,
                "product.template", "write",
                [to_fix_ids, {"taxes_id": [(6, 0, [target_tax_id])]}]
            )
            print(f"✅ Product taxes ready — {len(to_fix_ids)} product(s) updated to {TARGET_VAT_RATE}%", flush=True)
        else:
            print("✅ Product taxes ready — all products already have valid rates", flush=True)

        return tax_map_by_rate

    except Exception as e:
        print(f"⚠️  Could not verify/fix tax settings: {type(e).__name__}: {str(e)[:200]}", flush=True)
    return {}


def ensure_pos_categories(odoo_url, odoo_db, odoo_user, odoo_pass):
    print("🔍 Checking POS categories...", flush=True)
    try:
        common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
        models = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/object", allow_none=True)

        def get_or_create_category(name, color=1):
            existing = models.execute_kw(
                odoo_db, uid, odoo_pass, "pos.category", "search_read",
                [[["name", "=", name]]], {"fields": ["id"]}
            )
            if not existing:
                cat_id = models.execute_kw(
                    odoo_db, uid, odoo_pass, "pos.category", "create",
                    [{"name": name, "color": color}]
                )
                print(f"   ✅ Created POS category '{name}'", flush=True)
                return cat_id
            else:
                models.execute_kw(
                    odoo_db, uid, odoo_pass, "pos.category", "write",
                    [[existing[0]["id"]], {"color": color}]
                )
            return existing[0]["id"]

        topup_cat_id = get_or_create_category("Top-ups", 2)  # Light blue
        drinks_cat_id = get_or_create_category("Drinks", 3)  # Yellow
        return topup_cat_id, drinks_cat_id
    except Exception as e:
        print(f"⚠️  Could not verify POS categories: {e}", flush=True)
        return None, None


def ensure_payment_methods(odoo_url, odoo_db, odoo_user, odoo_pass):
    print("🔍 Checking POS payment methods...", flush=True)
    try:
        common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
        models = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/object", allow_none=True)

        needed = [
            {"name": "Cash", "is_cash_count": True},
            {"name": "Bancontact", "is_cash_count": False},
            {"name": "Badge Wallet", "is_cash_count": False}
        ]

        method_ids = []
        for method in needed:
            existing = models.execute_kw(
                odoo_db, uid, odoo_pass,
                "pos.payment.method", "search_read",
                [[["name", "=", method["name"]]]],
                {"fields": ["id"]}
            )
            if existing:
                method_ids.append(existing[0]["id"])
            else:
                pm_id = models.execute_kw(
                    odoo_db, uid, odoo_pass,
                    "pos.payment.method", "create",
                    [{"name": method["name"], "is_cash_count": method["is_cash_count"]}]
                )
                print(f"   ✅ Created payment method: {method['name']}", flush=True)
                method_ids.append(pm_id)

        return method_ids
    except Exception as e:
        print(f"⚠️  Could not verify payment methods: {e}", flush=True)
        return []


def ensure_demo_products(odoo_url, odoo_db, odoo_user, odoo_pass, topup_cat_id, drinks_cat_id, tax_map=None):
    print("🔍 Checking demo products...", flush=True)
    try:
        common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
        models = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/object", allow_none=True)

        def get_tax_id(rate):
            t = models.execute_kw(
                odoo_db, uid, odoo_pass, "account.tax", "search_read",
                [[["amount", "=", rate], ["type_tax_use", "in", ["sale", "all"]],
                  ["amount_type", "=", "division"], ["price_include_override", "=", "tax_included"]]],
                {"limit": 1}
            )
            return t[0]["id"] if t else None

        tax_0 = tax_map.get(0.0) if tax_map else get_tax_id(0.0)
        tax_6 = tax_map.get(6.0) if tax_map else get_tax_id(6.0)
        tax_21 = tax_map.get(21.0) if tax_map else get_tax_id(21.0)

        # list_price IS the final customer price (tax included) because we use amount_type='division'
        demo_products = [
            {
                "name": "Cola", "list_price": 2.50,
                "taxes_id": [(6, 0, [tax_6])] if tax_6 else [],
                "available_in_pos": True, "type": "consu", "color": 3, "image_1920": False,
                "pos_categ_ids": [(6, 0, [drinks_cat_id])] if drinks_cat_id else []
            },
            {
                "name": "Koffie", "list_price": 2.80,
                "taxes_id": [(6, 0, [tax_6])] if tax_6 else [],
                "available_in_pos": True, "type": "consu", "color": 3, "image_1920": False,
                "pos_categ_ids": [(6, 0, [drinks_cat_id])] if drinks_cat_id else []
            },
            {
                "name": "Pintje", "list_price": 3.00,
                "taxes_id": [(6, 0, [tax_21])] if tax_21 else [],
                "available_in_pos": True, "type": "consu", "x_age_restricted": True,
                "color": 3, "image_1920": False,
                "pos_categ_ids": [(6, 0, [drinks_cat_id])] if drinks_cat_id else []
            },
            {
                "name": "Top-up €10", "list_price": 10.00,
                "taxes_id": [(6, 0, [tax_0])] if tax_0 else [],
                "available_in_pos": True, "type": "service", "x_is_topup": True,
                "color": 2, "image_1920": False,
                "pos_categ_ids": [(6, 0, [topup_cat_id])] if topup_cat_id else []
            },
            {
                "name": "Top-up €20", "list_price": 20.00,
                "taxes_id": [(6, 0, [tax_0])] if tax_0 else [],
                "available_in_pos": True, "type": "service", "x_is_topup": True,
                "color": 2, "image_1920": False,
                "pos_categ_ids": [(6, 0, [topup_cat_id])] if topup_cat_id else []
            },
        ]

        for product in demo_products:
            existing = models.execute_kw(
                odoo_db, uid, odoo_pass,
                "product.template", "search_read",
                [[["name", "=", product["name"]]]],
                {"fields": ["id"]}
            )
            if not existing:
                models.execute_kw(
                    odoo_db, uid, odoo_pass,
                    "product.template", "create",
                    [product]
                )
                print(f"   ✅ Created demo product: {product['name']}", flush=True)
            else:
                models.execute_kw(
                    odoo_db, uid, odoo_pass, "product.template", "write",
                    [[existing[0]["id"]], {"color": product["color"], "image_1920": False}]
                )

    except Exception as e:
        print(f"⚠️  Could not create demo products: {e}", flush=True)


def ensure_pos_config(odoo_url, odoo_db, odoo_user, odoo_pass, pm_ids):
    print("🔍 Checking standard POS configuration...", flush=True)
    try:
        common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
        models = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/object", allow_none=True)

        desired_vals = {
            "limit_categories": False,
            "iface_tax_included": "total",
            "payment_method_ids": [(6, 0, pm_ids)],
        }

        configs = models.execute_kw(
            odoo_db, uid, odoo_pass,
            "pos.config", "search_read",
            [[["name", "=", "Bar Kassa"]]],
            {"fields": ["id"], "limit": 1}
        )

        if configs:
            config_id = configs[0]["id"]
            models.execute_kw(odoo_db, uid, odoo_pass, "pos.config", "write", [[config_id], desired_vals])
            print(f"   ✅ Updated 'Bar Kassa' POS config (id={config_id})", flush=True)
        else:
            desired_vals["name"] = "Bar Kassa"
            config_id = models.execute_kw(odoo_db, uid, odoo_pass, "pos.config", "create", [desired_vals])
            print(f"   ✅ Created POS configuration 'Bar Kassa' (id={config_id})", flush=True)

    except Exception as e:
        print(f"⚠️  Could not update POS config: {e}", flush=True)


def main():
    print("🚀 Kassa Integration Service Started", flush=True)
    print("📋 Flow: Odoo POS → Order Poller → Sender → RabbitMQ (+ outbox fallback)", flush=True)

    odoo_url = os.environ.get("ODOO_URL")
    odoo_db = os.environ.get("ODOO_DB")
    odoo_user = os.environ.get("ODOO_USER")
    odoo_pass = os.environ.get("ODOO_PASS")
    odoo_master_pass = os.environ.get("ODOO_MASTER_PASS")

    # Step 1: Wait for Odoo web server to be reachable
    if not wait_for_odoo(odoo_url):
        print("❌ Odoo web server did not become available. Exiting.", flush=True)
        sys.exit(1)

    # Step 2: Auto-create database if it doesn't exist
    if not setup_database(odoo_url, odoo_db, odoo_user, odoo_pass, odoo_master_pass):
        print("❌ Database setup failed. Exiting.", flush=True)
        sys.exit(1)

    # Step 3: Auto-install POS module if needed
    if not ensure_pos_installed(odoo_url, odoo_db, odoo_user, odoo_pass):
        print("❌ POS module installation failed. Exiting.", flush=True)
        sys.exit(1)

    # Step 4: Ensure custom Odoo fields exist (x_user_id, x_badge_id, etc.)
    ensure_custom_fields(odoo_url, odoo_db, odoo_user, odoo_pass)

    # Step 5: Configure tax settings globally
    tax_map = ensure_tax_settings(odoo_url, odoo_db, odoo_user, odoo_pass)

    # Step 6: Setup POS base data (categories, payment methods, demo products, pos.config)
    topup_cat_id, drinks_cat_id = ensure_pos_categories(odoo_url, odoo_db, odoo_user, odoo_pass)
    pm_ids = ensure_payment_methods(odoo_url, odoo_db, odoo_user, odoo_pass)
    ensure_demo_products(odoo_url, odoo_db, odoo_user, odoo_pass, topup_cat_id, drinks_cat_id, tax_map)
    ensure_pos_config(odoo_url, odoo_db, odoo_user, odoo_pass, pm_ids)

    # ── Receiver thread ────────────────────────────────────────────────────────
    receiver_thread = threading.Thread(
        target=_run_receiver,
        name="receiver",
        daemon=True,
    )
    receiver_thread.start()
    print("✅ Receiver thread started", flush=True)

    # Step 7: Initialize and start Order Poller
    print("📦 Starting Order Poller...", flush=True)
    poller = OrderPoller()

    if not poller.connect_odoo():
        print("❌ Failed to connect to Odoo", flush=True)
        sys.exit(1)

    # Try to flush any buffered messages from previous runs
    print("🔄 Checking for buffered messages...", flush=True)
    sender.flush_buffer()

    print("✅ Order Poller initialized successfully", flush=True)

    # Run poller in a thread
    poller_thread = threading.Thread(
        target=poller.poll, kwargs={
            'interval': int(
                os.environ.get(
                    "POLL_INTERVAL", 5))})
    poller_thread.daemon = True
    poller_thread.start()
    print("✅ Poller thread started", flush=True)

    print("✅ All services running. Press Ctrl+C to stop.", flush=True)

    # Keep main thread alive
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n🛑 Service shutdown requested – stopping service.", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
