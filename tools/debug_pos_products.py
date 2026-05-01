# tools/debug_pos_products.py
import os
import xmlrpc.client
from dotenv import load_dotenv

load_dotenv()

ODOO_URL = "http://localhost:8069"
ODOO_DB = "odoo_kassa"
ODOO_USER = "desiderius"
ODOO_PASS = "xT7#mK9vR2pL5nQ"

def debug():
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASS, {})
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

    print(f"--- POS Categories ---")
    pos_categs = models.execute_kw(ODOO_DB, uid, ODOO_PASS, 'pos.category', 'search_read', [[]], {'fields': ['id', 'name']})
    for c in pos_categs:
        print(f"ID: {c['id']}, Name: {c['name']}")

    print(f"\n--- Product Template Fields ---")
    fields = models.execute_kw(ODOO_DB, uid, ODOO_PASS, 'product.template', 'fields_get', [], {'attributes': ['string', 'type']})
    pos_fields = {k: v for k, v in fields.items() if 'pos' in k.lower()}
    for k, v in pos_fields.items():
        print(f"Field: {k}, Type: {v['type']}, String: {v['string']}")

    print(f"\n--- Products available in POS ---")
    products = models.execute_kw(ODOO_DB, uid, ODOO_PASS, 'product.template', 'search_read',
                                 [[['available_in_pos', '=', True]]],
                                 {'fields': ['id', 'name', 'default_code', 'categ_id', 'pos_categ_ids']})
    for p in products:
        print(f"ID: {p['id']}, Name: {p['name']}, Ref: {p['default_code']}, Categ: {p['categ_id']}, POS Categs: {p['pos_categ_ids']}")

    print(f"\n--- POS Configs ---")
    configs = models.execute_kw(ODOO_DB, uid, ODOO_PASS, 'pos.config', 'search_read', [[]],
                                {'fields': ['id', 'name', 'limit_categories', 'iface_available_categ_ids']})
    for c in configs:
        print(f"POS: {c['name']}, Limit Categs: {c['limit_categories']}, Allowed Categ IDs: {c['iface_available_categ_ids']}")

if __name__ == "__main__":
    debug()
