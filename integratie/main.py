# main.py – Kassa Integration Service entry point
# Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026
#
# Starts all integration components in separate daemon threads:
#   - receiver   → listens on queue.incoming (RabbitMQ)
#   - poller     → polls Odoo for new POS orders  (when available)
#   - heartbeat  → sends periodic heartbeat        (when available)

import os
import sys
import threading
import time
import xmlrpc.client
import requests

import receiver
import sender
from order_poller import OrderPoller


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
    """Auto-create the Odoo database if it doesn't exist yet"""
    print(f"🔍 Checking if database '{odoo_db}' exists...", flush=True)

    # First check if we can already authenticate (DB exists)
    try:
        common = xmlrpc.client.ServerProxy(
            f'{odoo_url}/xmlrpc/2/common', allow_none=True)
        uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
        if uid:
            print(
                f"✅ Database '{odoo_db}' already exists and is accessible",
                flush=True)
            return True
    except Exception:
        pass  # DB doesn't exist yet — proceed to create it

    print(
        f"📦 Database '{odoo_db}' not found — creating it automatically...",
        flush=True)

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
            print(
                f"✅ Database '{odoo_db}' initialized. Waiting for readiness...", flush=True)
            # Give Odoo a moment to finish initialization by polling for successful auth
            for _ in range(10):  # Poll for 50 seconds
                time.sleep(5)
                try:
                    common = xmlrpc.client.ServerProxy(
                        f'{odoo_url}/xmlrpc/2/common', allow_none=True)
                    uid = common.authenticate(
                        odoo_db, odoo_user, odoo_pass, {})
                    if uid:
                        print(
                            f"✅ Database '{odoo_db}' is now accessible.", flush=True)
                        return True
                except Exception:
                    pass  # Ignore connection errors during polling

            print(
                f"⚠️  Database '{odoo_db}' was created, but could not confirm accessibility.", flush=True)
            return False
        else:
            print(
                f"⚠️  Database creation returned status {resp.status_code}",
                flush=True)
            return False

    except Exception as e:
        print(f"❌ Could not auto-create database: {e}", flush=True)
        return False


def ensure_custom_fields(odoo_url, odoo_db, odoo_user, odoo_pass):
    """
    Create custom fields on res.partner and pos.order if they don't exist yet.
    Safe to call on every startup — skips fields that are already present.
    """
    FIELDS = {
        "res.partner": {
            "x_user_id":        ("char",    "External User ID"),
            "x_badge_id":       ("char",    "Badge ID"),
            "x_wallet_balance": ("float",   "Wallet Balance (EUR)"),
            "x_age":            ("integer", "Age"),
        },
        "pos.order": {
            "x_rabbitmq_sent": ("boolean", "Sent to RabbitMQ"),
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

            for fname, (ttype, label) in fields.items():
                if fname in existing:
                    continue
                models.execute_kw(
                    odoo_db, uid, odoo_pass,
                    "ir.model.fields", "create",
                    [{"model_id": model_id, "name": fname,
                      "field_description": label, "ttype": ttype, "store": True}],
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


VALID_VAT_RATES = {0, 6, 12, 21}
TARGET_VAT_RATE = 6


def ensure_product_taxes(odoo_url, odoo_db, odoo_user, odoo_pass):
    """
    Ensure all POS products have a valid VAT rate (0, 6, 12 or 21%).
    Products with non-standard rates are updated to TARGET_VAT_RATE.
    Safe to call on every startup — skips products already correctly configured.
    """
    print("🔍 Checking POS product tax rates...", flush=True)
    try:
        common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
        if not uid:
            print("⚠️  Cannot check product taxes — Odoo auth failed", flush=True)
            return

        models = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/object", allow_none=True)

        # Find or create target tax
        existing_tax = models.execute_kw(
            odoo_db, uid, odoo_pass,
            "account.tax", "search_read",
            [[["amount", "=", TARGET_VAT_RATE], ["type_tax_use", "in", ["sale", "all"]]]],
            {"fields": ["id", "name"], "limit": 1}
        )
        if existing_tax:
            target_tax_id = existing_tax[0]["id"]
        else:
            target_tax_id = models.execute_kw(
                odoo_db, uid, odoo_pass,
                "account.tax", "create",
                [{"name": f"BTW {TARGET_VAT_RATE}%", "amount": TARGET_VAT_RATE,
                  "type_tax_use": "sale", "amount_type": "percent"}]
            )
            print(f"   ✅ Created {TARGET_VAT_RATE}% tax", flush=True)

        # Check all POS products
        product_ids = models.execute_kw(
            odoo_db, uid, odoo_pass,
            "product.template", "search",
            [[["available_in_pos", "=", True]]]
        )
        if not product_ids:
            print("✅ No POS products found — skipping", flush=True)
            return

        products = models.execute_kw(
            odoo_db, uid, odoo_pass,
            "product.template", "read",
            [product_ids, ["id", "name", "taxes_id"]]
        )

        # Batch fetch all unique tax IDs in one call
        all_tax_ids = list({tid for p in products for tid in p.get("taxes_id", [])})
        tax_map = {}
        if all_tax_ids:
            taxes_data = models.execute_kw(
                odoo_db, uid, odoo_pass,
                "account.tax", "read",
                [all_tax_ids, ["amount"]]
            )
            tax_map = {t["id"]: t["amount"] for t in taxes_data}

        # Identify products that need fixing
        to_fix_ids = []
        for product in products:
            tax_ids = product.get("taxes_id", [])
            if not tax_ids:
                to_fix_ids.append(product["id"])
                continue
            rates = {int(tax_map.get(tid, 0)) for tid in tax_ids}
            if not rates.issubset(VALID_VAT_RATES):
                print(f"   Fixing '{product['name']}': {rates} → {TARGET_VAT_RATE}%", flush=True)
                to_fix_ids.append(product["id"])

        # Batch update all products in a single call
        if to_fix_ids:
            models.execute_kw(
                odoo_db, uid, odoo_pass,
                "product.template", "write",
                [to_fix_ids, {"taxes_id": [(6, 0, [target_tax_id])]}]
            )
            print(f"✅ Product taxes ready — {len(to_fix_ids)} product(s) updated to {TARGET_VAT_RATE}%",
                  flush=True)
        else:
            print("✅ Product taxes ready — all products already have valid rates", flush=True)

    except Exception as e:
        print(f"⚠️  Could not verify/fix product taxes: {type(e).__name__}: {str(e)[:200]}", flush=True)


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

    # Step 5: Fix non-standard product tax rates
    ensure_product_taxes(odoo_url, odoo_db, odoo_user, odoo_pass)

    # ── Receiver thread ────────────────────────────────────────────────────────
    receiver_thread = threading.Thread(
        target=_run_receiver,
        name="receiver",
        daemon=True,
    )
    receiver_thread.start()
    print("✅ Receiver thread started", flush=True)

    # Step 4: Initialize and start Order Poller
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
