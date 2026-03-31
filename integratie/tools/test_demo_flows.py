"""
test_demo_flows.py — End-to-end test voor Flow 1 (bedrijfsklant) en Flow 2 (anoniem)

Maakt echte orders aan in Odoo en wacht tot de poller ze oppikt.
Gebruik: docker exec kassa_integratie python tools/test_demo_flows.py
"""

import xmlrpc.client
import os
import sys

ODOO_URL = os.environ.get("ODOO_URL")
ODOO_DB = os.environ.get("ODOO_DB")
ODOO_USER = os.environ.get("ODOO_USER")
ODOO_PASS = os.environ.get("ODOO_PASS")

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


def get_open_session(uid, models):
    ids = models.execute_kw(ODOO_DB, uid, ODOO_PASS,
                            "pos.session", "search",
                            [[["state", "=", "opened"]]])
    if not ids:
        print("FOUT: geen actieve POS-sessie gevonden. Open een kassa-sessie in Odoo.")
        sys.exit(1)
    print(f"Actieve POS-sessie: {ids[0]}")
    return ids[0]


def get_any_product(uid, models):
    ids = models.execute_kw(ODOO_DB, uid, ODOO_PASS,
                            "product.product", "search",
                            [[["available_in_pos", "=", True]]], {"limit": 1})
    if not ids:
        # Fallback: any product
        ids = models.execute_kw(ODOO_DB, uid, ODOO_PASS,
                                "product.product", "search", [[]], {"limit": 1})
    if not ids:
        print("FOUT: geen producten gevonden in Odoo")
        sys.exit(1)
    name = models.execute_kw(ODOO_DB, uid, ODOO_PASS,
                             "product.product", "read", [ids[0], ["name"]])[0]["name"]
    print(f"Product voor test: [{ids[0]}] {name}")
    return ids[0]


def ensure_company_customer(uid, models):
    """Zoek of maak een bedrijf + contactpersoon voor Flow 1."""
    # Zoek bestaand testbedrijf
    company_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASS,
                                    "res.partner", "search",
                                    [[["name", "=", "Demo Testbedrijf NV"],
                                      ["is_company", "=", True]]])
    if company_ids:
        company_id = company_ids[0]
        print(f"Bestaand testbedrijf gevonden: id={company_id}")
    else:
        company_id = models.execute_kw(ODOO_DB, uid, ODOO_PASS,
                                       "res.partner", "create",
                                       [{"name": "Demo Testbedrijf NV",
                                         "is_company": True,
                                         "email": "info@demobedrijf.be"}])
        print(f"Nieuw testbedrijf aangemaakt: id={company_id}")

    # Zoek bestaande contactpersoon
    contact_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASS,
                                    "res.partner", "search",
                                    [[["name", "=", "Demo Jan Peeters"],
                                      ["parent_id", "=", company_id]]])
    if contact_ids:
        contact_id = contact_ids[0]
        print(f"Bestaande contactpersoon gevonden: id={contact_id}")
    else:
        contact_id = models.execute_kw(ODOO_DB, uid, ODOO_PASS,
                                       "res.partner", "create",
                                       [{"name": "Demo Jan Peeters",
                                         "is_company": False,
                                         "parent_id": company_id,
                                         "email": "jan.peeters@demobedrijf.be"}])
        print(f"Nieuwe contactpersoon aangemaakt: id={contact_id} (parent={company_id})")

    return contact_id


def create_order(uid, models, session_id, product_id, partner_id=False, label=""):
    """Maak een POS-order aan en zet hem op paid."""
    order_id = models.execute_kw(ODOO_DB, uid, ODOO_PASS,
                                 "pos.order", "create",
                                 [{"session_id": session_id,
                                   "partner_id": partner_id,
                                   "amount_tax": 0.0,
                                   "amount_total": 5.00,
                                   "amount_paid": 5.00,
                                   "amount_return": 0.0,
                                   "company_id": int(os.environ.get("ODOO_COMPANY_ID", 1))}])

    models.execute_kw(ODOO_DB, uid, ODOO_PASS,
                      "pos.order.line", "create",
                      [{"order_id": order_id,
                        "product_id": product_id,
                        "qty": 1,
                        "price_unit": 5.00,
                        "price_subtotal": 5.00,
                        "price_subtotal_incl": 5.00}])

    try:
        models.execute_kw(ODOO_DB, uid, ODOO_PASS,
                          "pos.order", "action_pos_order_paid", [order_id])
    except Exception:
        models.execute_kw(ODOO_DB, uid, ODOO_PASS,
                          "pos.order", "write",
                          [[order_id], {"state": "paid"}])

    partner_info = f"partner_id={partner_id}" if partner_id else "ANONIEM"
    print(f"Order aangemaakt: id={order_id}  ({partner_info})  [{label}]")
    return order_id


def main():
    print(SEP)
    print("DEMO FLOW TEST — Flow 1 (bedrijfsklant) + Flow 2 (anoniem)")
    print(SEP)

    uid, models = connect()
    session_id = get_open_session(uid, models)
    product_id = get_any_product(uid, models)

    print()
    print("--- FLOW 2: Anonieme aankoop ---")
    anon_id = create_order(uid, models, session_id, product_id,
                           partner_id=False, label="Flow 2 anoniem")

    print()
    print("--- FLOW 1: Klant gelinkt aan bedrijf ---")
    contact_id = ensure_company_customer(uid, models)
    company_id = create_order(uid, models, session_id, product_id,
                              partner_id=contact_id, label="Flow 1 bedrijfsklant")

    print()
    print(SEP)
    print("Beide orders staan op PAID in Odoo.")
    print(f"  Flow 2 (anoniem):       order id={anon_id}")
    print(f"  Flow 1 (bedrijfsklant): order id={company_id}")
    print()
    print("Poller interval is ~3s. Verwachte output hieronder:")
    print("  [poller] Order {id}: ANONYMOUS")
    print("  [poller] Order {id}: Demo Jan Peeters")
    print()
    print("Volg live met:")
    print("  docker logs -f kassa_integratie")
    print(SEP)


if __name__ == "__main__":
    main()
