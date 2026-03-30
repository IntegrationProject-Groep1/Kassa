import xmlrpc.client
import os
import sys


def ping_odoo():
    url = os.environ.get("ODOO_URL")
    db = os.environ.get("ODOO_DB")
    user = os.environ.get("ODOO_USER")
    password = os.environ.get("ODOO_PASS")

    print(f"Binnenkomende configuratie: URL={url}, DB={db}, USER={user}")
    print("Testen van verbinding met Odoo via XML-RPC...")

    try:
        # 1. Testen of Odoo uberhaupt aanstaat
        common = xmlrpc.client.ServerProxy(
            f'{url}/xmlrpc/2/common', allow_none=True
        )
        version_info = common.version()
        print("✅ Odoo bereikt! Odoo versie: "
              f"{version_info.get('server_version')}")
        # 2. Testen of inloggegevens kloppen en we toegang hebben
        print("Testen van authenticatie...")
        uid = common.authenticate(db, user, password, {})
        if uid:
            print(f"✅ Authenticatie geslaagd! User ID: {uid}")
            print("De XML-RPC verbinding werkt perfect. Integratiescripts "
                  "kunnen veilig data ophalen wegschrijven!")
        else:
            print("⚠️ Authenticatie mislukt. Controleer of de database "
                  "bestaat en de inloggegevens in .env correct zijn.")
            sys.exit(1)

    except ConnectionRefusedError:
        print("❌ Connectie geweigerd. Odoo container staat waarschijnlijk "
              "nog niet aan.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Kan Odoo niet bereiken of er is een fout opgetreden: {e}")
        sys.exit(1)


if __name__ == "__main__":
    ping_odoo()
