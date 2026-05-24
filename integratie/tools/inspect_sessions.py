import os
import sys
import xmlrpc.client
import defusedxml.xmlrpc
from dotenv import load_dotenv

# Mitigate XML vulnerabilities for xmlrpc.client (Bandit B411)
defusedxml.xmlrpc.monkey_patch()

# Load env variables from .env
load_dotenv()

url = os.environ.get("ODOO_URL")
db = os.environ.get("ODOO_DB")
user = os.environ.get("ODOO_USER")
password = os.environ.get("ODOO_PASS")

if not all([url, db, user, password]):
    print("Error: ODOO_URL, ODOO_DB, ODOO_USER, and ODOO_PASS must be set in the environment.")
    sys.exit(1)

# If running on the host, replace kassa-web with localhost
if "kassa-web" in url:
    url = url.replace("kassa-web", "localhost")

print(f"Connecting to Odoo at: {url}")
print(f"Database: {db}")
print(f"User: {user}")

try:
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, user, password, {})
    if not uid:
        print("❌ Authentication failed!")
        sys.exit(1)

    print(f"✅ Authenticated successfully! User ID: {uid}")

    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

    # Query all POS sessions
    sessions = models.execute_kw(
        db, uid, password, "pos.session", "search_read",
        [[]],
        {"fields": ["id", "name", "state", "config_id", "company_id"]}
    )

    print(f"\nFound {len(sessions)} POS Sessions:")
    for s in sessions:
        info = (
            f" - ID: {s['id']}, "
            f"Name: {s['name']}, "
            f"State: {s['state']}, "
            f"Config: {s['config_id']}, "
            f"Company: {s['company_id']}"
        )
        print(info)

except Exception as e:
    print(f"Error: {e}")
