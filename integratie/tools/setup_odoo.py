# setup_odoo.py – One-time Odoo setup for new team members
# Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026
#
# Creates all custom fields required by the Kassa integration if they do
# not already exist.  Safe to run multiple times – existing fields are
# detected and skipped.
#
# Usage (from project root):
#   python integratie/tools/setup_odoo.py
#
# Credentials are loaded from the .env file in the project root.
# Any variable already set in the environment takes priority over .env.
#
# Fields created:
#   res.partner
#     x_user_id        Char     external UUID, primary link key
#     x_badge_id       Char     RFID badge ID
#     x_wallet_balance Float    wallet balance in EUR
#     x_age            Integer  visitor age
#   pos.order
#     x_rabbitmq_sent  Boolean  True once the order has been published to RabbitMQ

import os
import sys
import xmlrpc.client
from pathlib import Path

from dotenv import load_dotenv

# ── Load .env (project root is two levels above this file) ─────────────────────
_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH, override=False)  # env vars already set take priority

ODOO_URL = os.environ.get("ODOO_URL")
ODOO_DB = os.environ.get("ODOO_DB")
ODOO_USER = os.environ.get("ODOO_USER")
ODOO_PASS = os.environ.get("ODOO_PASS")

# ── Field definitions grouped by Odoo model ───────────────────────────────────
FIELDS_BY_MODEL: dict[str, dict[str, dict]] = {
    "res.partner": {
        "x_user_id":        {"ttype": "char",    "string": "External User ID"},
        "x_badge_id":       {"ttype": "char",    "string": "Badge ID"},
        "x_wallet_balance": {"ttype": "float",   "string": "Wallet Balance (EUR)"},
        "x_age":            {"ttype": "integer", "string": "Age"},
    },
    "pos.order": {
        "x_rabbitmq_sent": {"ttype": "boolean", "string": "Sent to RabbitMQ"},
        "x_wallet_updated": {"ttype": "boolean", "string": "Wallet Refund Processed"},
    },
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_model_id(models, model_name: str) -> int:
    result = models.execute_kw(
        ODOO_DB, _uid, ODOO_PASS,
        "ir.model", "search_read",
        [[["model", "=", model_name]]],
        {"fields": ["id"], "limit": 1},
    )
    if not result:
        raise RuntimeError(f"Model '{model_name}' not found in Odoo – is the POS module installed?")
    return result[0]["id"]


def _existing_field_names(models, model_name: str, field_names: list[str]) -> set[str]:
    rows = models.execute_kw(
        ODOO_DB, _uid, ODOO_PASS,
        "ir.model.fields", "search_read",
        [[["model", "=", model_name], ["name", "in", field_names]]],
        {"fields": ["name"]},
    )
    return {r["name"] for r in rows}


def _create_field(models, model_id: int, fname: str, fdef: dict) -> int:
    return models.execute_kw(
        ODOO_DB, _uid, ODOO_PASS,
        "ir.model.fields", "create",
        [{
            "model_id":          model_id,
            "name":              fname,
            "field_description": fdef["string"],
            "ttype":             fdef["ttype"],
            "store":             True,
        }],
    )


# ── Main ───────────────────────────────────────────────────────────────────────

_uid: int = 0   # set after authentication


def main() -> None:
    global _uid

    print(f"[SETUP] Odoo  : {ODOO_URL}")
    print(f"[SETUP] DB    : {ODOO_DB}")
    print(f"[SETUP] User  : {ODOO_USER}")
    print(f"[SETUP] .env  : {_ENV_PATH}  (found={_ENV_PATH.exists()})")
    print()

    # ── Authenticate ──────────────────────────────────────────────────────────
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", allow_none=True)
    try:
        version_info = common.version()
        if not isinstance(version_info, dict):
            raise RuntimeError("Unexpected response from Odoo version()")
        version = str(version_info.get("server_version", "unknown"))
    except Exception as exc:
        print(f"[SETUP] ERROR: cannot reach Odoo at {ODOO_URL} – {exc}")
        sys.exit(1)

    authenticated_uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASS, {})
    if not isinstance(authenticated_uid, int) or authenticated_uid <= 0:
        print("[SETUP] ERROR: authentication failed – check ODOO_USER / ODOO_PASS / ODOO_DB")
        sys.exit(1)
    _uid = authenticated_uid

    print(f"[SETUP] Connected  (Odoo {version}, UID={_uid})")
    print()

    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)

    total_created = 0
    total_skipped = 0

    # ── Process each model ────────────────────────────────────────────────────
    for model_name, fields in FIELDS_BY_MODEL.items():
        print(f"[SETUP] Model: {model_name}")

        try:
            model_id = _get_model_id(models, model_name)
        except RuntimeError as exc:
            print(f"[SETUP]   SKIP – {exc}")
            print()
            continue

        existing = _existing_field_names(models, model_name, list(fields))

        for fname, fdef in fields.items():
            ttype = fdef["ttype"]
            label = fdef["string"]
            if fname in existing:
                print(f"[SETUP]   {fname:<22} ({ttype:<8})  already exists    – skipped")
                total_skipped += 1
            else:
                fid = _create_field(models, model_id, fname, fdef)
                print(f"[SETUP]   {fname:<22} ({ttype:<8})  created OK        (id={fid})  \"{label}\"")
                total_created += 1

        print()

    # ── Summary ───────────────────────────────────────────────────────────────
    print("─" * 55)
    if total_created:
        print(f"[SETUP] Done – {total_created} field(s) created, {total_skipped} skipped.")
    else:
        print(f"[SETUP] Done – all {total_skipped} field(s) already present, nothing to do.")


if __name__ == "__main__":
    main()
