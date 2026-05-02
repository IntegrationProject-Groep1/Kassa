import xmlrpc.client
import os

ODOO_URL = os.environ.get('ODOO_URL', 'http://localhost:8069')
ODOO_DB = os.environ.get('ODOO_DB', 'odoo_kassa')
ODOO_USER = os.environ.get('ODOO_USER', 'odoo')
ODOO_PASS = os.environ.get('ODOO_PASS')

if ODOO_PASS is None:
    print('ODOO_PASS not set in environment. Exiting.')
    raise SystemExit(1)

common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", allow_none=True)
uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASS, {})
if not uid:
    print('Authentication failed')
    raise SystemExit(1)

models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)

products = models.execute_kw(ODOO_DB, uid, ODOO_PASS, 'product.template', 'search_read', [[
                             ['available_in_pos', '=', True]]], {'fields': ['id', 'name', 'default_code']})
print('Found products (available_in_pos=True):')
for p in products:
    print(p)

# Also print pos categories
cats = models.execute_kw(ODOO_DB, uid, ODOO_PASS, 'pos.category', 'search_read', [[
                         ['name', 'in', ['Top-ups', 'Drinks']]]], {'fields': ['id', 'name']})
print('\nPOS categories:')
for c in cats:
    print(c)
