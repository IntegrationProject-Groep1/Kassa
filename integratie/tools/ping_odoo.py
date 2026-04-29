import defusedxml.xmlrpc
defusedxml.xmlrpc.monkey_patch()  # Patch xmlrpc.client to use defusedxml
import xmlrpc.client  # nosec B411 - mitigated by monkey_patch above
import os
import sys


def ping_odoo():
    url = os.environ.get("ODOO_URL")
    db = os.environ.get("ODOO_DB")
    user = os.environ.get("ODOO_USER")
    password = os.environ.get("ODOO_PASS")

    print(f"Configuration: URL={url}, DB={db}, USER={user}")
    print("Testing Odoo connection via XML-RPC...")

    try:
        # 1. Check if Odoo is reachable
        common = xmlrpc.client.ServerProxy(
            f'{url}/xmlrpc/2/common', allow_none=True
        )
        version_info = common.version()
        print(f"✅ Odoo reachable! Version: {version_info.get('server_version')}")
        # 2. Check credentials and access
        print("Testing authentication...")
        uid = common.authenticate(db, user, password, {})
        if uid:
            print(f"✅ Authentication successful! User ID: {uid}")
            print("XML-RPC connection working. Integration scripts can safely read and write data.")
        else:
            print("⚠️ Authentication failed. Check that the database exists "
                  "and credentials in .env are correct.")
            sys.exit(1)

    except ConnectionRefusedError:
        print("❌ Connection refused. The Odoo container is probably not running yet.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Cannot reach Odoo or an error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    ping_odoo()
