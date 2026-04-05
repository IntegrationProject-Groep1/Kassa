"""
fix_product_taxes.py — Zet BTW-tarief van POS-producten naar 6%

Zoekt alle producten die beschikbaar zijn in POS en een BTW-tarief hebben
dat niet in de toegestane waarden (0, 6, 12, 21) staat, en past dit aan.

Gebruik: docker exec kassa_integratie python tools/fix_product_taxes.py
"""

import os
import sys
import xmlrpc.client

ODOO_URL = os.environ.get("ODOO_URL")
ODOO_DB = os.environ.get("ODOO_DB")
ODOO_USER = os.environ.get("ODOO_USER")
ODOO_PASS = os.environ.get("ODOO_PASS")

VALID_VAT_RATES = {0, 6, 12, 21}
TARGET_VAT_RATE = 6

SEP = "-" * 60


def connect():
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", allow_none=True)
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASS, {})
    if not uid:
        print("FOUT: Odoo authenticatie mislukt")
        sys.exit(1)
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)
    print(f"Odoo verbonden (uid={uid})")
    return uid, models


def get_or_create_tax(uid, models, rate):
    """Zoek een bestaande BTW van {rate}% of maak er een aan."""
    existing = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "account.tax", "search_read",
        [[["amount", "=", rate], ["type_tax_use", "in", ["sale", "all"]]]],
        {"fields": ["id", "name", "amount"], "limit": 1}
    )
    if existing:
        tax = existing[0]
        print(f"Bestaande {rate}% BTW gevonden: [{tax['id']}] {tax['name']}")
        return tax["id"]

    tax_id = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "account.tax", "create",
        [{"name": f"BTW {rate}%", "amount": rate, "type_tax_use": "sale",
          "amount_type": "percent"}]
    )
    print(f"Nieuwe {rate}% BTW aangemaakt: id={tax_id}")
    return tax_id


def fix_product_taxes(uid, models, target_tax_id):
    """Pas BTW aan op alle POS-producten met een niet-toegelaten tarief."""
    product_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "product.template", "search",
        [[["available_in_pos", "=", True]]]
    )

    if not product_ids:
        print("Geen POS-producten gevonden.")
        return

    products = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "product.template", "read",
        [product_ids, ["id", "name", "taxes_id"]]
    )

    # Batch fetch all unique tax IDs in one call
    all_tax_ids = list({tid for p in products for tid in p.get("taxes_id", [])})
    tax_map = {}
    if all_tax_ids:
        taxes_data = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "account.tax", "read",
            [all_tax_ids, ["amount"]]
        )
        tax_map = {t["id"]: t["amount"] for t in taxes_data}

    # Identify products that need fixing
    to_fix = []
    for product in products:
        tax_ids = product.get("taxes_id", [])
        if not tax_ids:
            to_fix.append(product)
            continue
        rates = {int(tax_map.get(tid, -1)) for tid in tax_ids}
        if not rates.issubset(VALID_VAT_RATES):
            to_fix.append(product)
            print(f"  [{product['id']}] {product['name']} — tarief(en): {rates} → wordt aangepast")

    if not to_fix:
        print("Alle POS-producten hebben al een geldig BTW-tarief.")
        return

    # Batch update all products in a single call
    to_fix_ids = [p["id"] for p in to_fix]
    print(f"\n{len(to_fix_ids)} product(en) worden aangepast naar {TARGET_VAT_RATE}%...")
    models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "product.template", "write",
        [to_fix_ids, {"taxes_id": [(6, 0, [target_tax_id])]}]
    )
    for product in to_fix:
        print(f"  ✅ [{product['id']}] {product['name']}")

    print(f"\n✅ {len(to_fix)} product(en) bijgewerkt naar {TARGET_VAT_RATE}% BTW.")


def main():
    print(SEP)
    print(f"FIX PRODUCT TAXES — Zet niet-standaard BTW naar {TARGET_VAT_RATE}%")
    print(f"Toegestane tarieven: {sorted(VALID_VAT_RATES)}")
    print(SEP)

    uid, models = connect()
    print()

    target_tax_id = get_or_create_tax(uid, models, TARGET_VAT_RATE)
    print()

    fix_product_taxes(uid, models, target_tax_id)
    print(SEP)


if __name__ == "__main__":
    main()
