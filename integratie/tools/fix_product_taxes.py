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

    to_fix = []
    for product in products:
        tax_ids = product.get("taxes_id", [])
        if not tax_ids:
            to_fix.append(product)
            continue

        taxes = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "account.tax", "read",
            [tax_ids, ["amount"]]
        )
        rates = {int(t["amount"]) for t in taxes}
        if not rates.issubset(VALID_VAT_RATES):
            to_fix.append(product)
            print(f"  [{product['id']}] {product['name']} — tarief(en): {rates} → wordt aangepast")

    if not to_fix:
        print("Alle POS-producten hebben al een geldig BTW-tarief.")
        return

    print(f"\n{len(to_fix)} product(en) worden aangepast naar {TARGET_VAT_RATE}%...")
    for product in to_fix:
        models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "product.template", "write",
            [[product["id"]], {"taxes_id": [(6, 0, [target_tax_id])]}]
        )
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
