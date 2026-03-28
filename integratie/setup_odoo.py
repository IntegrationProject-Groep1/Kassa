# setup_odoo.py – One-time setup script for Odoo custom fields
# Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026
#
# Creates the 4 custom fields required on res.partner if they do not exist yet.
# Run once after a fresh Odoo database is created:
#
#   python integratie/setup_odoo.py
#
# Fields created on res.partner:
#   x_user_id        (Char)    – external UUID, primary link key
#   x_badge_id       (Char)    – RFID badge ID
#   x_wallet_balance (Float)   – wallet balance in EUR
#   x_age            (Integer) – visitor age

import os
import sys
import xmlrpc.client

ODOO_URL  = os.environ.get("ODOO_URL",  "http://localhost:8069")
ODOO_DB   = os.environ.get("ODOO_DB",   "odoo_kassa")
ODOO_USER = os.environ.get("ODOO_USER", "odoo")
ODOO_PASS = os.environ.get("ODOO_PASS", "myodoo")

REQUIRED_FIELDS = {
    "x_user_id":        {"ttype": "char",    "string": "External User ID"},
    "x_badge_id":       {"ttype": "char",    "string": "Badge ID"},
    "x_wallet_balance": {"ttype": "float",   "string": "Wallet Balance (EUR)"},
    "x_age":            {"ttype": "integer", "string": "Age"},
}


def main() -> None:
    print(f"[SETUP] Connecting to Odoo: {ODOO_URL}  db={ODOO_DB}  user={ODOO_USER}")

    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", allow_none=True)
    uid    = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASS, {})
    if not uid:
        print("[SETUP] ERROR: authentication failed – check ODOO_USER / ODOO_PASS / ODOO_DB")
        sys.exit(1)

    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)

    # Find which fields already exist
    existing = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "ir.model.fields", "search_read",
        [[["model", "=", "res.partner"], ["name", "in", list(REQUIRED_FIELDS)]]],
        {"fields": ["name"]},
    )
    existing_names = {f["name"] for f in existing}

    # Get the res.partner model id (needed for ir.model.fields create)
    model_info = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "ir.model", "search_read",
        [[["model", "=", "res.partner"]]],
        {"fields": ["id"], "limit": 1},
    )
    model_id = model_info[0]["id"]

    created = []
    for fname, fdef in REQUIRED_FIELDS.items():
        if fname in existing_names:
            print(f"[SETUP]   {fname}: already exists – skipped")
            continue
        fid = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "ir.model.fields", "create",
            [{
                "model_id": model_id,
                "name":     fname,
                "field_description": fdef["string"],
                "ttype":    fdef["ttype"],
                "store":    True,
            }],
        )
        print(f"[SETUP]   {fname}: created (ir.model.fields id={fid})")
        created.append(fname)

    if created:
        print(f"[SETUP] Done – created {len(created)} field(s): {', '.join(created)}")
    else:
        print("[SETUP] Done – all fields already present, nothing to do.")


if __name__ == "__main__":
    main()
