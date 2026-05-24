import os
import xmlrpc.client
from dotenv import load_dotenv

# Load env variables from .env
load_dotenv()

url = os.environ.get("ODOO_URL", "http://localhost:8069")
# If running on the host, replace kassa-web with localhost
if "kassa-web" in url:
    url = url.replace("kassa-web", "localhost")

db = os.environ.get("ODOO_DB", "odoo_kassa")
user = os.environ.get("ODOO_USER", "desiderius")
password = os.environ.get("ODOO_PASS", "xT7#mK9vR2pL5nQ")

print(f"Connecting to Odoo at: {url}")
print(f"Database: {db}")
print(f"User: {user}")

try:
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, user, password, {})
    if not uid:
        print("❌ Authentication failed!")
        exit(1)
    
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
        print(f" - ID: {s['id']}, Name: {s['name']}, State: {s['state']}, Config: {s['config_id']}, Company: {s['company_id']}")

except Exception as e:
    print(f"❌ Error: {e}")
