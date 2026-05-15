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

# Ensure categories
print('Ensuring POS categories Top-ups and Drinks')
for name in ['Top-ups', 'Drinks']:
    recs = models.execute_kw(ODOO_DB, uid, ODOO_PASS, 'pos.category', 'search_read', [
                             [['name', '=', name]]], {'fields': ['id'], 'limit': 1})
    if recs:
        print(f'Category {name} exists, id={recs[0]["id"]}')
    else:
        cid = models.execute_kw(ODOO_DB, uid, ODOO_PASS, 'pos.category', 'create', [{'name': name}])
        print(f'Created category {name} id={cid}')

# Ensure payment methods
print('\nEnsuring payment methods Cash, Card, Badge Wallet')
for method, is_cash, extra in [('Cash', True, {}), ('Card', False, {}), ('Badge Wallet', False, {'split_transactions': True})]:
    recs = models.execute_kw(ODOO_DB, uid, ODOO_PASS, 'pos.payment.method', 'search_read', [
                             [['name', '=', method]]], {'fields': ['id'], 'limit': 1})
    if recs:
        print(f'Payment method {method} exists, id={recs[0]["id"]}')
    else:
        vals = {'name': method, 'is_cash_count': is_cash}
        vals.update(extra)
        pid = models.execute_kw(ODOO_DB, uid, ODOO_PASS, 'pos.payment.method', 'create', [vals])
        print(f'Created payment method {method} id={pid}')

# Create demo products
print('\nCreating demo products')
products = [
    ("Top-up EUR 10", "TOPUP-010", 10.0, 'Top-ups', 0.0, {'x_is_topup': True}),
    ("Top-up EUR 20", "TOPUP-020", 20.0, 'Top-ups', 0.0, {'x_is_topup': True}),
    ("Top-up Algemeen", "TOPUP-ALG", 0.0, 'Top-ups', 0.0, {'x_is_topup': True}),
    ("Cola", "DRINK-001", 2.50, 'Drinks', 21.0, {}),
    ("Water", "DRINK-002", 1.80, 'Drinks', 6.0, {}),
    ("Coffee", "DRINK-003", 2.20, 'Drinks', 6.0, {}),
    ("Beer", "DRINK-004", 3.00, 'Drinks', 21.0, {'x_age_restricted': True}),
]

for name, ref, price, cat_name, tax_rate, extra in products:
    cat = models.execute_kw(ODOO_DB, uid, ODOO_PASS, 'pos.category', 'search_read', [
                            [['name', '=', cat_name]]], {'fields': ['id'], 'limit': 1})
    pos_categ_id = cat[0]['id'] if cat else False
    tax_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASS, 'account.tax', 'search', [
                                [['amount', '=', tax_rate], ['type_tax_use', '=', 'sale'], ['amount_type', '=', 'percent'], ['price_include', '=', True]]])
    tax_id = tax_ids[0] if tax_ids else False
    existing = models.execute_kw(ODOO_DB, uid, ODOO_PASS, 'product.template', 'search_read', [
                                 [['default_code', '=', ref]]], {'fields': ['id'], 'limit': 1})
    vals = {
        'name': name,
        'default_code': ref,
        'list_price': price,
        'type': 'consu',
        'pos_categ_ids': [[6, 0, [pos_categ_id]]] if pos_categ_id else False,
        'available_in_pos': True
    }
    if tax_id:
        vals['taxes_id'] = [[6, 0, [tax_id]]]
    vals.update(extra)
    if existing:
        models.execute_kw(ODOO_DB, uid, ODOO_PASS, 'product.template', 'write', [[existing[0]['id']], vals])
        print(f'Updated product {name}')
    else:
        pid = models.execute_kw(ODOO_DB, uid, ODOO_PASS, 'product.template', 'create', [vals])
        print(f'Created product {name} id={pid}')
