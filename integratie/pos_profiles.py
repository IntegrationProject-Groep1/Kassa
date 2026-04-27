# pos_profiles.py — POS profile setup for the Kassa integration service
# Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026
#
# Creates two POS configurations in Odoo if they don't exist yet:
#   - "Bar Kassa"          → Cash, Card, Badge Wallet
#   - "Inschrijvingskassa" → Cash (Inschrijving), Card
#
# Odoo does not allow a cash payment method (is_cash_count=True) to be used in
# more than one POS config.  "Cash (Inschrijving)" is therefore created with
# is_cash_count=False — cash counting is not required for a registration desk.

import xmlrpc.client
from typing import Any, cast

from odoo_setup import _extract_company_id

# Each payment method entry is a dict with:
#   "name"              – exact Odoo name to look up
#   "create_if_missing" – optional dict of extra fields passed to create()
#                         when the method does not yet exist in Odoo.
#                         Omit this key for methods that must already exist
#                         (created by ensure_payment_methods in main.py).
_PROFILES: list[dict[str, Any]] = [
    {
        "name": "Bar Kassa",
        "payment_methods": [
            {"name": "Cash"},
            {"name": "Card"},
            {"name": "Badge Wallet"},
        ],
        "categ_names": ["Drinks", "Top-ups"],
    },
    {
        "name": "Inschrijvingskassa",
        "payment_methods": [
            {"name": "Cash (Inschrijving)", "create_if_missing": {"is_cash_count": False}},
            {"name": "Card"},
        ],
        "categ_names": ["Top-ups"],
    },
]

_SHARED_VALS = {
    "iface_tax_included": "total",
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

    user_info = cast(list[dict[str, Any]], models.execute_kw(
        db, uid, password, "res.users", "read", [[uid], ["company_id"]]
    ))
    company_id: int | None = _extract_company_id(user_info)

    # Build a name→id map for pos.category so profiles can filter by category
    all_categs = cast(list[dict[str, Any]], models.execute_kw(
        db, uid, password, "pos.category", "search_read",
        [[]], {"fields": ["id", "name"]},
    ))
    categ_map: dict[str, int] = {c["name"]: c["id"] for c in all_categs}

    # Archive unmanaged configs first so their cash methods are freed before we resolve
    _archive_unmanaged_pos_configs(models, db, uid, password,
                                   keep={p["name"] for p in _PROFILES},
                                   company_id=company_id)

    # ── Phase 1: resolve / create all payment methods ─────────────────────
    all_pm_ids: dict[str, list] = {}
    for profile in _PROFILES:
        pm_ids, resolved_names = _resolve_payment_method_ids(
            models, db, uid, password, profile, company_id
        )

        # Check specifically for critical methods: "Cash" and "Card"
        critical_names = {"Cash", "Card"} & {pm["name"] for pm in profile["payment_methods"]}
        missing_critical = critical_names - resolved_names

        if missing_critical:
            raise RuntimeError(
                f"Critical payment method(s) {missing_critical} not resolved for '{profile['name']}': "
                f"these are required to properly configure the Point of Sale."
            )

        all_pm_ids[profile["name"]] = pm_ids
        print(f"   🔑 '{profile['name']}' payment method IDs: {pm_ids}", flush=True)

    # ── Phase 2: create / update pos.config records ───────────────────────
    for profile in _PROFILES:
        categ_ids = [categ_map[n] for n in profile.get("categ_names", []) if n in categ_map]
        _upsert_pos_config(
            models, db, uid, password,
            profile["name"], all_pm_ids[profile["name"]], company_id, categ_ids,
        )

    print("✅ POS profiles ready", flush=True)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _archive_unmanaged_pos_configs(
    models: xmlrpc.client.ServerProxy,
    db: str,
    uid: int,
    password: str,
    keep: set[str],
    company_id: int | None = None,
) -> None:
    """Archive any pos.config records whose name is not in *keep* (e.g. Odoo's default 'Shop')."""
    domain: list = [["active", "=", True]]
    if company_id:
        domain.append(["company_id", "=", company_id])
    all_configs = cast(list[dict[str, Any]], models.execute_kw(
        db, uid, password,
        "pos.config", "search_read",
        [domain],
        {"fields": ["id", "name"]},
    ))
    to_archive = [c for c in all_configs if c["name"] not in keep]
    if not to_archive:
        return
    models.execute_kw(db, uid, password, "pos.config", "write",
                      [[c["id"] for c in to_archive], {"active": False}])
    for c in to_archive:
        print(f"   🗑️  Archived unmanaged POS config '{c['name']}'", flush=True)


def _resolve_payment_method_ids(
    models: xmlrpc.client.ServerProxy,
    db: str,
    uid: int,
    password: str,
    profile: dict[str, Any],
    company_id: int | None = None,
) -> tuple[list[int], set[str]]:
    """Return a tuple of (pos.payment.method IDs, set of resolved names) for the entries listed in *profile*.

    For entries with a 'create_if_missing' key the method is created in Odoo
    when it does not exist yet.  All other missing methods are skipped with a
    warning (they are expected to be created by ensure_payment_methods).
    """
    pm_ids = []
    resolved_names = set()
    for pm_spec in profile["payment_methods"]:
        name = pm_spec["name"]
        domain: list = [["name", "=", name]]
        if company_id:
            domain.append(["company_id", "=", company_id])
        result = cast(list[dict[str, Any]], models.execute_kw(
            db, uid, password,
            "pos.payment.method", "search_read",
            [domain],
            {"fields": ["id", "is_cash_count"], "limit": 1},
        ))
        if result:
            found_id = cast(int, result[0]["id"])
            # If a method exists but was manually created with mismatched flags,
            # normalize it to the expected value for this profile.
            if "create_if_missing" in pm_spec and "is_cash_count" in pm_spec["create_if_missing"]:
                expected_is_cash_count = bool(pm_spec["create_if_missing"]["is_cash_count"])
                current_is_cash_count = bool(result[0].get("is_cash_count"))
                if current_is_cash_count != expected_is_cash_count:
                    models.execute_kw(
                        db, uid, password,
                        "pos.payment.method", "write",
                        [[found_id], {"is_cash_count": expected_is_cash_count}],
                    )
                    print(
                        f"   🔧 Normalized payment method '{name}' is_cash_count "
                        f"{current_is_cash_count} → {expected_is_cash_count}",
                        flush=True,
                    )
            print(f"   🔍 Found payment method '{name}' → id={found_id}", flush=True)
            pm_ids.append(found_id)
            resolved_names.add(name)
        elif "create_if_missing" in pm_spec:
            create_vals = {"name": name, **pm_spec["create_if_missing"]}
            if company_id:
                create_vals["company_id"] = company_id
            new_id = cast(int, models.execute_kw(
                db, uid, password,
                "pos.payment.method", "create",
                [create_vals],
            ))
            print(f"   ✅ Created payment method '{name}' → id={new_id}", flush=True)
            pm_ids.append(new_id)
            resolved_names.add(name)
        else:
            print(
                f"   ⚠️  Payment method '{name}' not found "
                f"— skipping for '{profile['name']}'",
                flush=True,
            )
    return pm_ids, resolved_names


def _upsert_pos_config(
    models: xmlrpc.client.ServerProxy,
    db: str,
    uid: int,
    password: str,
    name: str,
    pm_ids: list[int],
    company_id: int | None = None,
    categ_ids: list[int] | None = None,
) -> int:
    """Create or update a pos.config record. Returns the record id."""
    domain: list = [["name", "=", name]]
    if company_id:
        domain.append(["company_id", "=", company_id])
    existing = cast(list[dict[str, Any]], models.execute_kw(
        db, uid, password,
        "pos.config", "search_read",
        [domain],
        {"fields": ["id"], "limit": 1},
    ))

    if existing:
        config_id = cast(int, existing[0]["id"])
        write_vals = {
            **_SHARED_VALS,
            "limit_categories": bool(categ_ids),
            "payment_method_ids": [(6, 0, pm_ids)],
        }
        if categ_ids:
            write_vals["iface_available_categ_ids"] = [(6, 0, categ_ids)]

        try:
            models.execute_kw(db, uid, password, "pos.config", "write", [[config_id], write_vals])
        except xmlrpc.client.Fault as fault:
            if not (
                "payment_method_ids" in write_vals
                and _is_cash_method_conflict_fault(fault)
            ):
                raise

            recovered_pm_ids = _replace_conflicting_cash_methods(
                models, db, uid, password, name, pm_ids, company_id,
            )
            if recovered_pm_ids == pm_ids:
                raise
            write_vals["payment_method_ids"] = [(6, 0, recovered_pm_ids)]
            models.execute_kw(db, uid, password, "pos.config", "write", [[config_id], write_vals])

        print(f"   ✅ Updated POS profile '{name}' (id={config_id})", flush=True)
        return config_id

    vals: dict = {
        **_SHARED_VALS,
        "payment_method_ids": [(6, 0, pm_ids)],
        "name": name,
        "limit_categories": bool(categ_ids),
    }
    if categ_ids:
        vals["iface_available_categ_ids"] = [(6, 0, categ_ids)]
    if company_id:
        vals["company_id"] = company_id
    try:
        config_id = cast(int, models.execute_kw(db, uid, password, "pos.config", "create", [vals]))
    except xmlrpc.client.Fault as fault:
        if not _is_cash_method_conflict_fault(fault):
            raise

        recovered_pm_ids = _replace_conflicting_cash_methods(
            models, db, uid, password, name, pm_ids, company_id,
        )
        if recovered_pm_ids == pm_ids:
            raise

        vals["payment_method_ids"] = [(6, 0, recovered_pm_ids)]
        config_id = cast(int, models.execute_kw(db, uid, password, "pos.config", "create", [vals]))

    print(f"   ✅ Created POS profile '{name}' (id={config_id})", flush=True)
    return config_id


def _is_cash_method_conflict_fault(fault: xmlrpc.client.Fault) -> bool:
    """Return True if an XML-RPC fault matches Odoo's cash payment method exclusivity error."""
    return "cash payment method is already used in another point of sale" in fault.faultString.lower()


def _replace_conflicting_cash_methods(
    models: xmlrpc.client.ServerProxy,
    db: str,
    uid: int,
    password: str,
    profile_name: str,
    pm_ids: list[int],
    company_id: int | None = None,
) -> list[int]:
    """Swap shared cash-count methods with profile-specific methods to satisfy Odoo constraints."""
    methods = cast(list[dict[str, Any]], models.execute_kw(
        db, uid, password,
        "pos.payment.method", "read",
        [pm_ids, ["id", "name", "is_cash_count"]],
    ))

    replacement_map: dict[int, int] = {}
    for method in methods:
        method_id = cast(int, method["id"])
        if not bool(method.get("is_cash_count")):
            continue

        base_name = cast(str, method.get("name") or "Cash")
        dedicated_name = f"{base_name} ({profile_name})"

        dedicated_domain: list = [["name", "=", dedicated_name]]
        if company_id:
            dedicated_domain.append(["company_id", "=", company_id])
        dedicated = cast(list[dict[str, Any]], models.execute_kw(
            db, uid, password,
            "pos.payment.method", "search_read",
            [dedicated_domain],
            {"fields": ["id"], "limit": 1},
        ))
        if dedicated:
            dedicated_id = cast(int, dedicated[0]["id"])
        else:
            create_vals: dict = {"name": dedicated_name, "is_cash_count": True}
            if company_id:
                create_vals["company_id"] = company_id
            dedicated_id = cast(int, models.execute_kw(
                db, uid, password,
                "pos.payment.method", "create",
                [create_vals],
            ))
            print(
                f"   ✅ Created dedicated cash method '{dedicated_name}' → id={dedicated_id}",
                flush=True,
            )

        replacement_map[method_id] = dedicated_id

    resolved_pm_ids = [replacement_map.get(pm_id, pm_id) for pm_id in pm_ids]
    if resolved_pm_ids != pm_ids:
        print(
            f"   🔧 Resolved cash-method conflict for '{profile_name}' by using dedicated cash method(s)",
            flush=True,
        )
    return resolved_pm_ids
