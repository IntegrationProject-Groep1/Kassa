"""
Diagnostic tool to test the local customer linking flow.
Creates a new partner in Odoo and monitors the PartnerIdentityPoller's progress.
"""
import os
import time

try:
    # Prefer defusedxml's xmlrpc interface for safe parsing (Bandit B411 mitigation)
    from defusedxml import xmlrpc
    # Apply monkey patch so stdlib xmlrpc is replaced with defusedxml's safe impl
    xmlrpc.monkey_patch()
except Exception:
    # Fall back to stdlib xmlrpc if defusedxml isn't installed in this environment
    pass

import xmlrpc.client

from datetime import datetime


def test_linking():
    url = os.environ.get("ODOO_URL")
    db = os.environ.get("ODOO_DB")
    user = os.environ.get("ODOO_USER")
    password = os.environ.get("ODOO_PASS")

    email = f"test.user.{int(time.time())}@example.com"
    name = f"Test User {datetime.now().strftime('%H:%M:%S')}"

    print(f"🚀 Testing Local Customer Linking for: {email}")

    try:
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(db, user, password, {})
        models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)

        # 1. Create a minimal partner
        print(f"📝 Creating partner '{name}' in Odoo...")
        partner_id = models.execute_kw(db, uid, password, "res.partner", "create", [{
            "name": name,
            "email": email,
        }])
        print(f"✅ Partner created with Odoo ID: {partner_id}")

        # 2. Monitor status
        print(f"⏳ Waiting for PartnerIdentityPoller to link {email} (check logs for Identity RPC)...")

        start_time = time.time()
        timeout = 60  # 1 minute

        while time.time() - start_time < timeout:
            partner = models.execute_kw(db, uid, password, "res.partner", "read", [
                [partner_id], ["x_user_id", "x_identity_status", "x_rabbitmq_error"]
            ])[0]

            status = partner.get("x_identity_status")
            uuid = partner.get("x_user_id")
            error = partner.get("x_rabbitmq_error")

            if status == "linked" and uuid:
                print("\n✨ SUCCESS! Partner linked successfully.")
                print(f"   Identity master_uuid: {uuid}")
                print(f"   Odoo Status: {status}")
                return

            if status == "error":
                print("\n❌ FAILED: Identity linking error.")
                print(f"   Error in Odoo: {error}")
                return

            print(f"   Current status: {status or 'waiting...'} (Elapsed: {int(time.time() - start_time)}s)", end="\r")
            time.sleep(2)

        print(f"\n⌛ TIMEOUT: Poller did not process the partner within {timeout}s.")
        print("   Check if the integration service is running and identity-poller thread is active.")

    except Exception as e:
        print(f"❌ Error during test: {e}")


if __name__ == "__main__":
    test_linking()
