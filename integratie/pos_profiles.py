# pos_profiles.py — POS profile setup for the Kassa integration service
# Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026
#
# Creates two POS configurations in Odoo if they don't exist yet:
#   - "Bar Kassa"          → Cash, Bancontact, Badge Wallet
#   - "Inschrijvingskassa" → Cash (Inschrijving), Bancontact
#
# Odoo does not allow a cash payment method (is_cash_count=True) to be used in
# more than one POS config.  "Cash (Inschrijving)" is therefore created with
# is_cash_count=False — cash counting is not required for a registration desk.

import xmlrpc.client

# Each payment method entry is a dict with:
#   "name"              – exact Odoo name to look up
#   "create_if_missing" – optional dict of extra fields passed to create()
#                         when the method does not yet exist in Odoo.
#                         Omit this key for methods that must already exist
#                         (created by ensure_payment_methods in main.py).
_PROFILES = [
    {
        "name": "Bar Kassa",
        "payment_methods": [
            {"name": "Cash"},
            {"name": "Bancontact"},
            {"name": "Badge Wallet"},
        ],
    },
    {
        "name": "Inschrijvingskassa",
        "payment_methods": [
            {"name": "Cash (Inschrijving)", "create_if_missing": {"is_cash_count": False}},
            {"name": "Bancontact"},
        ],
    },
]

_SHARED_VALS = {
    "iface_tax_included": "total",
    "limit_categories": False,
}


def ensure_pos_profiles(url: str, db: str, uid: int, password: str) -> None:
    """
    Create or update the two canonical POS configurations.

    Idempotent: searches for each profile by name first.
    If it already exists it is updated; otherwise it is created.

    Two-phase execution guarantees ordering:
      Phase 1 – resolve / create ALL payment methods across all profiles.
      Phase 2 – create / update ALL pos.config records.
    This prevents Odoo from raising "cash method already in use" when a
    freshly created pos.payment.method is immediately referenced in the
    same request cycle.

    Parameters
    ----------
    url      : Odoo base URL, e.g. "http://localhost:8069"
    db       : Odoo database name
    uid      : authenticated Odoo user id (integer, from common.authenticate)
    password : Odoo user password (used as the credentials token in execute_kw)
    """
    print("🔍 Checking POS profiles...", flush=True)
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)

    # ── Phase 1: resolve / create all payment methods ─────────────────────
    all_pm_ids: dict[str, list] = {}
    for profile in _PROFILES:
        pm_ids = _resolve_payment_method_ids(models, db, uid, password, profile)
        required_names = {pm["name"] for pm in profile["payment_methods"] if "create_if_missing" not in pm}
        if not pm_ids and ({"Cash", "Bancontact"} & required_names):
            raise RuntimeError(
                f"No payment method IDs resolved for '{profile['name']}': "
                f"Cash or Bancontact is required but none were found."
            )
        all_pm_ids[profile["name"]] = pm_ids
        print(f"   🔑 '{profile['name']}' payment method IDs: {pm_ids}", flush=True)

    # ── Phase 2: create / update pos.config records ───────────────────────
    for profile in _PROFILES:
        _upsert_pos_config(
            models, db, uid, password,
            profile["name"], all_pm_ids[profile["name"]],
        )

    print("✅ POS profiles ready", flush=True)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_payment_method_ids(
    models: xmlrpc.client.ServerProxy,
    db: str,
    uid: int,
    password: str,
    profile: dict,
) -> list:
    """Return a list of pos.payment.method IDs for the entries listed in *profile*.

    For entries with a 'create_if_missing' key the method is created in Odoo
    when it does not exist yet.  All other missing methods are skipped with a
    warning (they are expected to be created by ensure_payment_methods).
    """
    pm_ids = []
    for pm_spec in profile["payment_methods"]:
        name = pm_spec["name"]
        result = models.execute_kw(
            db, uid, password,
            "pos.payment.method", "search_read",
            [[["name", "=", name]]],
            {"fields": ["id"], "limit": 1},
        )
        if result:
            found_id = result[0]["id"]
            print(f"   🔍 Found payment method '{name}' → id={found_id}", flush=True)
            pm_ids.append(found_id)
        elif "create_if_missing" in pm_spec:
            new_id = models.execute_kw(
                db, uid, password,
                "pos.payment.method", "create",
                [{"name": name, **pm_spec["create_if_missing"]}],
            )
            print(f"   ✅ Created payment method '{name}' → id={new_id}", flush=True)
            pm_ids.append(new_id)
        else:
            print(
                f"   ⚠️  Payment method '{name}' not found "
                f"— skipping for '{profile['name']}'",
                flush=True,
            )
    return pm_ids


def _upsert_pos_config(
    models: xmlrpc.client.ServerProxy,
    db: str,
    uid: int,
    password: str,
    name: str,
    pm_ids: list,
) -> int:
    """Create or update a pos.config record. Returns the record id.

    When updating an existing config, payment_method_ids is only included in
    the write payload when the current set differs from the desired set.
    This avoids Odoo's 'cash method already in use' error on a no-op update.
    """
    existing = models.execute_kw(
        db, uid, password,
        "pos.config", "search_read",
        [[["name", "=", name]]],
        {"fields": ["id", "payment_method_ids"], "limit": 1},
    )

    if existing:
        config_id = existing[0]["id"]
        current_pm_ids = set(existing[0].get("payment_method_ids", []))
        desired_pm_ids = set(pm_ids)

        write_vals = {**_SHARED_VALS}
        if current_pm_ids != desired_pm_ids:
            write_vals["payment_method_ids"] = [(6, 0, pm_ids)]
            print(
                f"   🔄 Updating payment methods for '{name}': "
                f"{sorted(current_pm_ids)} → {sorted(desired_pm_ids)}",
                flush=True,
            )
        else:
            print(
                f"   ✅ Payment methods for '{name}' unchanged — skipping pm write",
                flush=True,
            )

        models.execute_kw(db, uid, password, "pos.config", "write", [[config_id], write_vals])
        print(f"   ✅ Updated POS profile '{name}' (id={config_id})", flush=True)
        return config_id

    vals = {
        **_SHARED_VALS,
        "payment_method_ids": [(6, 0, pm_ids)],
        "name": name,
    }
    config_id = models.execute_kw(db, uid, password, "pos.config", "create", [vals])
    print(f"   ✅ Created POS profile '{name}' (id={config_id})", flush=True)
    return config_id
