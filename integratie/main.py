import time
import sys
import os
import threading
import xmlrpc.client
import requests
from order_poller import OrderPoller
import sender


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


def main():
    print("🚀 Kassa Integration Service Started", flush=True)
    print(
        "📋 Flow: Odoo POS → Order Poller → Sender → RabbitMQ (+ outbox fallback)",
        flush=True)

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
    print("✅ All services running. Press Ctrl+C to stop.", flush=True)

    # Run poller in a thread
    poller_thread = threading.Thread(
        target=poller.poll, kwargs={
            'interval': int(
                os.environ.get(
                    "POLL_INTERVAL", 5))})
    poller_thread.daemon = True
    poller_thread.start()

    # Keep main thread alive
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n🛑 Service shutdown requested...", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
