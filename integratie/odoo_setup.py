"""
odoo_setup.py — Odoo bootstrap helpers for the Kassa integration service.
Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026

All functions here run once at startup (called from main.py) and are idempotent:
re-running them against an already-configured Odoo database is safe and produces
no duplicates. This is intentional — it allows container restarts without manual
database cleanup.

Configuration via XML-RPC (not Odoo modules) is a deliberate choice: it keeps
the CI pipeline fast and avoids the complexity of maintaining a full Odoo module
just to set a few fields.
"""

from __future__ import annotations

import time
import xmlrpc.client  # nosec
from typing import Any, cast

import defusedxml.xmlrpc
import requests

from typing_utils import OdooModelsProxy

defusedxml.xmlrpc.monkey_patch()


def _rpc(models: OdooModelsProxy, *args: Any, **kwargs: Any) -> Any:
    """Thin wrapper around execute_kw that centralises the call site for easier mocking in tests."""
    return models.execute_kw(*args, **kwargs)


def _extract_company_id(user_info: list[dict[str, Any]] | None) -> int | None:
    """Extract the integer company ID from a res.users read result.

    Odoo returns company_id as a [id, name] list when fetched via read(), or as a
    bare integer in some contexts. This handles both forms defensively.
    """
    if not user_info:
        return None
    company = user_info[0].get("company_id")
    if isinstance(company, (list, tuple)) and company:
        return int(company[0])
    if isinstance(company, int):
        return company
    return None


def _common_and_models(odoo_url: str) -> tuple[Any, Any]:
    """Return (common, models) XML-RPC proxies for the given Odoo URL.

    Odoo XML-RPC uses a two-phase authentication model:
    - `common.authenticate(db, user, pass, {})` → returns uid (int)
    - `models.execute_kw(db, uid, pass, model, method, args)` → data operations

    Both proxies are stateless; there is no persistent session to maintain.
    """
    common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common", allow_none=True)
    models = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/object", allow_none=True)
    return common, models


def wait_for_odoo(url: str, timeout: int = 300) -> bool:
    """Poll the Odoo web server until it responds or timeout expires.

    Any HTTP response (including 500) is treated as "reachable" — Odoo returns
    500 when the web server is up but no database exists yet, which is expected
    on first boot. A connection error or timeout means Odoo is not up yet.

    Default timeout is 300 s because a cold Odoo startup with module install and
    database initialisation on constrained CI nodes can take 2-4 minutes.
    """
    print(f"Waiting for Odoo at {url}...", flush=True)
    attempts = max(1, timeout // 5)

    for _ in range(attempts):
        try:
            # We accept ANY status code (even 500) as "reachable".
            # Odoo often returns 500 when no database is created yet,
            # but the web server is up and ready for /web/database/create.
            requests.get(url, timeout=5)
            print("Odoo is reachable.", flush=True)
            return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(5)

    print(f"Odoo was not reachable within {timeout}s", flush=True)
    return False


def setup_database(
    odoo_url: str,
    odoo_db: str,
    odoo_user: str,
    odoo_pass: str,
    odoo_master_pass: str,
    odoo_load_demo: bool = False,
) -> bool:
    """Create the Odoo database if it does not exist, then wait until it is authenticatable.

    Steps:
    1. Call ``db_exist`` on the Odoo DB service to check for the database.
       Falls back to an authentication attempt if the RPC call fails (some
       Odoo deployments disable the ``db_exist`` endpoint).
    2. If not found, call ``create_database`` with the master password.
       The master password is set in the Odoo config or via ``ODOO_MASTER_PASS``.
    3. Poll ``common.authenticate`` until either the target user or ``admin`` can log in
       (Odoo initialises the database in the background; this can take up to 20 minutes
       on CI nodes).  If ``admin`` logs in but the target user does not exist yet,
       ``_ensure_custom_user`` creates or updates it.

    Args:
        odoo_url:       Full base URL, e.g. ``http://odoo:8069``.
        odoo_db:        Name of the database to create or verify.
        odoo_user:      Integration service username (e.g. ``kassa``).
        odoo_pass:      Password for *odoo_user* — also used as the admin password
                        when creating a fresh database.
        odoo_master_pass: Odoo master (superadmin) password for DB operations.
                          Pass ``None`` or ``""`` if the master password is disabled.
        odoo_load_demo: Whether to load Odoo's built-in demo data. Only useful for
                        local development; always ``False`` in production.

    Returns:
        ``True`` when authentication succeeded, ``False`` on any unrecoverable error.
    """
    try:
        db_service = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/db", allow_none=True)
        common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common", allow_none=True)

        # 1. Check if database exists without needing authentication
        db_exists = False
        try:
            db_exists = bool(db_service.db_exist(odoo_db))
        except Exception as e:
            print(f"Could not check database existence: {e}. Trying authentication check...", flush=True)
            try:
                uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
                db_exists = bool(uid)
            except Exception:
                pass

        # 2. Create if it doesn't exist
        if not db_exists:
            print(f"Database '{odoo_db}' not found. Attempting to create (this may take a few minutes)...", flush=True)
            try:
                # Odoo 17 create_database(master_pwd, name, demo, lang, admin_password)
                # This always creates an 'admin' user with odoo_pass.
                db_service.create_database(odoo_master_pass, odoo_db, odoo_load_demo, 'en_US', odoo_pass)
                print("Database creation request sent successfully.", flush=True)
            except Exception as e:
                if "already exists" in str(e).lower():
                    print(f"Database '{odoo_db}' already exists (caught during create).", flush=True)
                else:
                    print(f"Database creation failed: {e}", flush=True)
                    return False

        # 3. Wait for the database to be authenticatable
        # We try both the configured user AND 'admin' (because fresh DBs only have admin).
        # Odoo database initialisation on constrained k8s nodes can take 10-15 min,
        # so we wait up to 20 minutes before giving up.
        timeout_seconds = 1200
        print(f"Waiting for database '{odoo_db}' to become available (up to {timeout_seconds//60} min)...", flush=True)
        deadline = time.time() + timeout_seconds
        uid = None
        elapsed_report = 0
        while time.time() < deadline:
            try:
                # Try target user first
                uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
                if uid:
                    print(f"✓ Authenticated as '{odoo_user}'", flush=True)
                    return True

                # If target user failed, try 'admin' (fallback for fresh installs)
                if odoo_user != "admin":
                    uid = common.authenticate(odoo_db, "admin", odoo_pass, {})
                    if uid:
                        print(f"✓ Authenticated as 'admin' (need to setup user '{odoo_user}')", flush=True)
                        # We are in! Now ensure our custom user exists.
                        _ensure_custom_user(odoo_url, odoo_db, odoo_user, odoo_pass)
                        return True
            except Exception:
                pass
            time.sleep(10)
            elapsed_report += 10
            if elapsed_report % 60 == 0:
                remaining = int(deadline - time.time())
                print(f"Still waiting for database '{odoo_db}'... ({remaining}s remaining)", flush=True)

        print(f"Database '{odoo_db}' was not available after {timeout_seconds//60} minutes.", flush=True)
        return False
    except Exception as e:
        print(f"Unexpected error in setup_database: {e}", flush=True)
        return False


def _ensure_custom_user(odoo_url: str, odoo_db: str, odoo_user: str, odoo_pass: str) -> None:
    """Create or update the integration-service Odoo user when only ``admin`` exists.

    Fresh Odoo databases only have the ``admin`` account.  This function is called
    from ``setup_database`` when ``admin`` authenticates but the target user
    (e.g. ``kassa``) does not yet exist.  It clones the admin group memberships so
    the integration service has full access to POS and partner data.

    If the user already exists, only the password is updated (idempotent).
    All errors are swallowed with a warning; failing here must not abort startup
    because the admin session is still valid and the service can continue.
    """
    try:
        common, models = _common_and_models(odoo_url)
        # Login as admin to create the user
        admin_uid = common.authenticate(odoo_db, "admin", odoo_pass, {})
        if not admin_uid:
            return

        # Check if user exists
        existing = _rpc(models, odoo_db, admin_uid, odoo_pass, "res.users", "search_read",
                        [[["login", "=", odoo_user]]], {"fields": ["id"]})

        if not existing:
            print(f"Creating user '{odoo_user}'...", flush=True)
            # Create user (cloning admin for groups)
            admin_data = _rpc(models, odoo_db, admin_uid, odoo_pass, "res.users", "read",
                              [[admin_uid]], {"fields": ["groups_id"]})

            groups_ids = admin_data[0].get("groups_id", []) if admin_data else []

            _rpc(models, odoo_db, admin_uid, odoo_pass, "res.users", "create", [{
                "name": odoo_user.capitalize(),
                "login": odoo_user,
                "password": odoo_pass,
                "groups_id": [[6, 0, groups_ids]],
            }])
        else:
            print(f"Updating password for user '{odoo_user}'...", flush=True)
            _rpc(models, odoo_db, admin_uid, odoo_pass, "res.users", "write",
                 [[existing[0]["id"]], {"password": odoo_pass}])
    except Exception as e:
        print(f"⚠️ Could not ensure custom user '{odoo_user}': {e}", flush=True)


def ensure_pos_installed(odoo_url: str, odoo_db: str, odoo_user: str, odoo_pass: str) -> bool:
    """Install the ``point_of_sale`` Odoo module if it is not already installed.

    Checks the current state of the ``ir.module.module`` record for
    ``point_of_sale``.  If the state is not ``installed``, calls
    ``button_immediate_install`` and polls (max 300 s) until installation completes.

    Returns:
        ``True`` if POS is installed (or was just installed successfully).
        ``False`` if the module record was not found or authentication failed.
    """
    common, models = _common_and_models(odoo_url)
    uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
    if not uid:
        return False

    module_ids = _rpc(
        models,
        odoo_db,
        uid,
        odoo_pass,
        "ir.module.module",
        "search",
        [[["name", "=", "point_of_sale"]]],
        {"limit": 1},
    )
    if not module_ids:
        return False

    module_id = module_ids[0]
    module_state = _rpc(
        models, odoo_db, uid, odoo_pass, "ir.module.module", "read",
        [[module_id]], {"fields": ["state"]}
    )
    if module_state and module_state[0].get("state") == "installed":
        return True

    _rpc(
        models, odoo_db, uid, odoo_pass, "ir.module.module",
        "button_immediate_install", [[module_id]]
    )
    deadline = time.time() + 300
    while time.time() < deadline:
        module_state = _rpc(
            models, odoo_db, uid, odoo_pass, "ir.module.module", "read",
            [[module_id]], {"fields": ["state"]}
        )
        if module_state and module_state[0].get("state") == "installed":
            return True
        time.sleep(5)
    return False


def ensure_kassa_addons(odoo_url: str, odoo_db: str, odoo_user: str, odoo_pass: str) -> bool:
    """Install the ``kassa_pos_custom`` Odoo addon if it is present and not yet installed.

    The addon is optional — if it does not appear in ``ir.module.module`` (e.g. the
    module directory is not mounted) the function silently skips it without failing.

    Upgrade is intentionally skipped: ``button_immediate_upgrade`` triggers a full
    Odoo registry reload that terminates all active POS sessions.  Schema upgrades
    are handled via the ``--update=kassa_pos_custom`` flag on container startup instead.

    Returns:
        ``True`` always (failures are non-fatal — the service can still run without
        the custom addon, albeit with reduced functionality).
    """
    common, models = _common_and_models(odoo_url)
    uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
    if not uid:
        return False

    for addon_name in ["kassa_pos_custom"]:
        module_ids = _rpc(
            models,
            odoo_db,
            uid,
            odoo_pass,
            "ir.module.module",
            "search",
            [[["name", "=", addon_name]]],
            {"limit": 1},
        )
        if not module_ids:
            continue
        module_id = module_ids[0]
        module_state = _rpc(
            models, odoo_db, uid, odoo_pass, "ir.module.module", "read",
            [[module_id]], {"fields": ["state"]}
        )
        state = module_state[0].get("state") if module_state else None
        if state == "installed":
            print(f"Addon '{addon_name}' is already installed — skipping upgrade.", flush=True)
        elif state in ("to upgrade", "to install", "uninstalled"):
            print(f"Installing addon '{addon_name}'...", flush=True)
            _rpc(models, odoo_db, uid, odoo_pass, "ir.module.module",
                 "button_immediate_install", [[module_id]])
        else:
            # Odoo already handles upgrades via --update=kassa_pos_custom on startup.
            # Calling button_immediate_upgrade here triggers a registry reload that
            # wipes all active sessions, causing login loops for logged-in users.
            print(f"Addon '{addon_name}' is in state '{state}' — skipping.", flush=True)
    return True


def ensure_custom_fields(odoo_url: str, odoo_db: str, odoo_user: str, odoo_pass: str) -> bool:
    """Create all Kassa custom fields in Odoo if they do not already exist.

    Custom fields extend standard Odoo models (``res.partner``, ``pos.order``, etc.)
    with Kassa-specific data.  They are created via ``ir.model.fields`` so no Odoo
    module is required — the service can bootstrap a vanilla Odoo install at runtime.

    Field creation is batched into a single ``create`` call to minimise round-trips.
    Existing fields are left untouched; field definitions are never modified here to
    avoid accidental data loss (e.g. changing a char field to an integer would clear
    all existing values).

    Returns:
        ``True`` when the check completed (even if some models were not found).
        ``False`` if authentication failed.

    Note:
        This function is NOT called by ``main.py`` in production — the custom addon
        ``kassa_pos_custom`` declares all fields via Odoo's standard module mechanism.
        This function exists as a fallback for environments where the addon is absent.
    """
    print("Checking custom fields...", flush=True)
    common, models = _common_and_models(odoo_url)
    uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
    if not uid:
        return False

    fields_to_check: list[tuple[str, str, str, str, dict[str, Any]]] = [
        ("res.partner", "x_user_id", "External CRM User ID", "char", {"index": True}),
        ("res.partner", "x_badge_id", "IoT Badge ID", "char", {"index": True}),
        ("res.partner", "x_badge_sent", "Badge Assignment Sent to CRM", "boolean", {}),
        ("res.partner", "x_wallet_balance", "Visitor Wallet Balance", "float", {}),
        ("res.partner", "x_pending_topup_balance", "Pending Top-up (pre-lease)", "float", {}),
        ("res.partner", "x_date_of_birth", "Date of Birth", "date", {}),
        ("res.partner", "x_session_id", "Session ID", "char", {}),
        ("res.partner", "x_session_title", "Session Title", "char", {}),
        ("res.partner", "x_outstanding_amount", "Outstanding Amount", "float", {}),
        ("res.partner", "x_payment_status", "Payment Status", "char", {}),
        ("product.template", "x_session_id", "Planning Session ID", "char", {"index": True}),
        ("product.template", "x_is_topup", "Top-up Product", "boolean", {}),
        ("product.template", "x_age_restricted", "Age Restricted", "boolean", {}),
        ("pos.order", "x_rabbitmq_sent", "Sent to CRM via RabbitMQ", "boolean", {}),
        ("pos.order", "x_wallet_updated", "Wallet Balance Adjusted", "boolean", {}),
        ("pos.order", "x_payment_message_id", "CRM Payment Correlation ID", "char", {}),
        ("pos.order", "x_invoice_message_id", "Invoice Request Message ID", "char", {}),
        ("pos.order", "x_rabbitmq_error", "RabbitMQ Integration Error", "text", {}),
        ("res.partner", "x_rabbitmq_error", "RabbitMQ Integration Error", "text", {}),
        ("res.partner", "x_lease_active",            "Wallet Lease Active",        "boolean", {}),
        ("res.partner", "x_lease_id",                "Wallet Lease ID",             "char",    {}),
        ("res.partner", "x_lease_transaction_count", "Lease Transaction Count",     "integer", {}),
        ("res.partner", "x_identity_status", "Identity Linking Status", "selection", {
            "selection": [["pending", "Pending"], ["linked", "Linked"], ["error", "Error"]]
        }),
        ("res.partner", "x_identity_last_sync", "Last Identity Sync", "datetime", {}),
    ]

    fields_to_create = []

    for model, name, field_description, field_type, field_kwargs in fields_to_check:
        existing = _rpc(
            models,
            odoo_db,
            uid,
            odoo_pass,
            "ir.model.fields",
            "search_read",
            [[["model", "=", model], ["name", "=", name]]],
            {"fields": ["id"], "limit": 1},
        )
        if existing:
            continue

        model_records = _rpc(
            models,
            odoo_db,
            uid,
            odoo_pass,
            "ir.model",
            "search_read",
            [[["model", "=", model]]],
            {"fields": ["id"], "limit": 1},
        )
        if not model_records:
            print(f"Model '{model}' not found, skipping field creation for '{name}'.", flush=True)
            continue

        create_vals = {
            "name": name,
            "field_description": field_description,
            "model_id": model_records[0]["id"],
            "ttype": field_type,
            "state": "manual",
        }
        create_vals.update(field_kwargs)
        fields_to_create.append(create_vals)

    if fields_to_create:
        print(f"Creating {len(fields_to_create)} missing custom fields in batch...", flush=True)
        _rpc(models, odoo_db, uid, odoo_pass, "ir.model.fields", "create", [fields_to_create])

    return True


def ensure_tax_settings(odoo_url: str, odoo_db: str, odoo_user: str, odoo_pass: str) -> dict[float, int]:
    """Ensure Belgian VAT tax records exist and configure the company currency to EUR.

    Creates ``account.tax`` records for the four Belgian VAT rates (0%, 6%, 12%, 21%)
    as price-inclusive sales taxes.  "Price inclusive" means the entered price already
    contains the tax — this matches how POS prices are shown on the display.

    Also sets the company's tax rounding method to ``round_per_line`` (Belgian
    accounting requirement) and activates EUR as the company currency if needed.

    Returns:
        A ``{rate: tax_id}`` dict, e.g. ``{0.0: 5, 6.0: 6, 12.0: 7, 21.0: 8}``.
        Passed to ``ensure_demo_products`` so products are linked to the correct tax.
        Returns an empty dict on authentication failure.
    """
    common, models = _common_and_models(odoo_url)
    uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
    if not uid:
        return {}

    user_info = _rpc(models, odoo_db, uid, odoo_pass, "res.users",
                     "read", [[uid]], {"fields": ["company_id"]})
    company_id = _extract_company_id(user_info)

    tax_map: dict[float, int] = {}
    for rate in (0.0, 6.0, 12.0, 21.0):
        taxes = _rpc(
            models,
            odoo_db,
            uid,
            odoo_pass,
            "account.tax",
            "search_read",
            [
                [
                    ["amount", "=", rate],
                    ["type_tax_use", "=", "sale"],
                    ["amount_type", "=", "percent"],
                    ["price_include", "=", True]
                ]
            ],
            {"fields": ["id"], "limit": 1},
        )
        if taxes:
            tax_map[rate] = taxes[0]["id"]
            continue

        tax_map[rate] = _rpc(
            models,
            odoo_db,
            uid,
            odoo_pass,
            "account.tax",
            "create",
            [{
                "name": f"{int(rate)}% Sales Tax (Incl.)",
                "amount": rate,
                "amount_type": "percent",
                "type_tax_use": "sale",
                "price_include": True,
            }],
        )

    if company_id:
        eur_currencies = _rpc(
            models, odoo_db, uid, odoo_pass, "res.currency", "search_read",
            [[["name", "=", "EUR"]]], {"fields": ["id", "active"], "limit": 1, "context": {"active_test": False}}
        )
        # Always safe — not currency-related.
        _rpc(
            models, odoo_db, uid, odoo_pass, "res.company", "write",
            [[company_id], {"tax_calculation_rounding_method": "round_per_line"}]
        )
        if eur_currencies:
            eur_id = eur_currencies[0]["id"]
            if not eur_currencies[0].get("active"):
                _rpc(
                    models, odoo_db, uid, odoo_pass, "res.currency", "write",
                    [[eur_id], {"active": True}]
                )
            current_company = _rpc(
                models, odoo_db, uid, odoo_pass, "res.company", "read",
                [[company_id]], {"fields": ["currency_id"]}
            )
            curr = current_company[0].get("currency_id") if current_company else None
            curr_id = curr[0] if isinstance(curr, (list, tuple)) and curr else curr
            if curr_id != eur_id:
                try:
                    _rpc(
                        models, odoo_db, uid, odoo_pass, "res.company", "write",
                        [[company_id], {"currency_id": eur_id}]
                    )
                except xmlrpc.client.Fault as exc:
                    print(f"[WARN] Could not set company currency to EUR: {exc.faultString}", flush=True)

    return tax_map


def ensure_pos_categories(odoo_url: str, odoo_db: str, odoo_user: str, odoo_pass: str) -> tuple[int, int, int]:
    """Create the three canonical POS product categories if they do not exist.

    The three categories are:
    - **Top-ups** — wallet top-up products (``x_is_topup=True``).  Used by
      ``is_topup_product()`` in the order poller to detect top-up lines.
    - **Drinks** — consumable items sold at the bar.
    - **Sessions** — conference/workshop sessions added dynamically by
      ``_ensure_session_product()`` in the receiver when ``session_created``
      or ``user_sessions_response`` messages arrive.

    Returns:
        ``(topup_cat_id, drinks_cat_id, sessions_cat_id)`` — Odoo integer IDs.
        Returns ``(0, 0, 0)`` on authentication failure.
    """
    common, models = _common_and_models(odoo_url)
    uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
    if not uid:
        return 0, 0, 0

    def _ensure_category(name: str) -> int:
        records = _rpc(
            models,
            odoo_db,
            uid,
            odoo_pass,
            "pos.category",
            "search_read",
            [[["name", "=", name]]],
            {"fields": ["id"], "limit": 1, "context": {}},
        )
        if records:
            return records[0]["id"]
        return _rpc(models, odoo_db, uid, odoo_pass, "pos.category", "create", [{"name": name}], {"context": {}})

    return _ensure_category("Top-ups"), _ensure_category("Drinks"), _ensure_category("Sessions")


def ensure_payment_methods(odoo_url: str, odoo_db: str, odoo_user: str, odoo_pass: str) -> list[int]:
    """Create the three standard POS payment methods if they do not exist.

    Payment methods:
    - **Cash** (``is_cash_count=True``) — physical cash; Odoo counts denominations.
    - **Card** (``is_cash_count=False``) — card terminal; no cash tracking needed.
    - **Badge Wallet** (``is_cash_count=False``, ``split_transactions=True``) —
      deducts from the visitor's ``x_wallet_balance``.  ``split_transactions=True``
      allows the cashier to split a single order across wallet + another method.

    All three are created under the current user's company so multi-company installs
    do not mix payment methods between tenants.

    Returns:
        ``[cash_id, card_id, badge_wallet_id]`` — Odoo integer IDs.
        Returns an empty list on authentication failure.
    """
    common, models = _common_and_models(odoo_url)
    uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
    if not uid:
        return []

    user_info = _rpc(models, odoo_db, uid, odoo_pass, "res.users",
                     "read", [[uid]], {"fields": ["company_id"]})
    company_id = _extract_company_id(user_info)

    def _ensure_method(name: str, is_cash_count: bool, extra_vals: dict[str, Any] | None = None) -> int:
        domain: list[list[str | int | bool]] = [["name", "=", name]]
        if company_id is not None:
            domain.append(["company_id", "=", company_id])

        records = _rpc(
            models,
            odoo_db,
            uid,
            odoo_pass,
            "pos.payment.method",
            "search_read",
            [domain],
            {"fields": ["id"], "limit": 1},
        )
        if records:
            return cast(int, records[0]["id"])

        vals: dict[str, Any] = {"name": name, "is_cash_count": is_cash_count}
        if extra_vals:
            vals.update(extra_vals)
        if company_id is not None:
            vals["company_id"] = company_id
        return cast(int, _rpc(models, odoo_db, uid, odoo_pass, "pos.payment.method", "create", [vals]))

    result: list[int] = [
        _ensure_method("Cash", True),
        _ensure_method("Card", False),
        _ensure_method("Badge Wallet", False, {"split_transactions": True}),
    ]
    return result


def ensure_demo_products(
    odoo_url: str,
    odoo_db: str,
    odoo_user: str,
    odoo_pass: str,
    topup_cat_id: int,
    drinks_cat_id: int,
    tax_map: dict[float, int],
) -> None:
    """Create or update the canonical demo products for Bar Kassa and Top-ups.

    Products are identified by ``default_code`` (internal reference) so they can
    be updated on subsequent restarts without creating duplicates.  Each product
    is placed in the correct POS category and linked to the appropriate VAT tax
    from ``tax_map``.

    Product list:
    - Top-up EUR 10/20 and Top-up Algemeen (0% VAT, ``x_is_topup=True``)
    - Cola/Beer (21% VAT), Water/Coffee (6% VAT), Beer also has ``x_age_restricted=True``

    Args:
        topup_cat_id:  POS category ID for Top-ups (from ``ensure_pos_categories``).
        drinks_cat_id: POS category ID for Drinks (from ``ensure_pos_categories``).
        tax_map:       ``{rate: tax_id}`` dict (from ``ensure_tax_settings``).
    """
    common, models = _common_and_models(odoo_url)
    uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
    if not uid:
        return

    products: list[tuple[str, str, float, int, float, dict[str, Any]]] = [
        ("Top-up EUR 10", "TOPUP-010", 10.0, topup_cat_id, 0.0, {"x_is_topup": True}),
        ("Top-up EUR 20", "TOPUP-020", 20.0, topup_cat_id, 0.0, {"x_is_topup": True}),
        ("Top-up Algemeen", "TOPUP-ALG", 0.0, topup_cat_id, 0.0, {"x_is_topup": True}),
        ("Cola", "DRINK-001", 2.50, drinks_cat_id, 21.0, {}),
        ("Water", "DRINK-002", 1.80, drinks_cat_id, 6.0, {}),
        ("Coffee", "DRINK-003", 2.20, drinks_cat_id, 6.0, {}),
        ("Beer", "DRINK-004", 3.00, drinks_cat_id, 21.0, {"x_age_restricted": True}),
    ]

    for name, ref, price, pos_cat_id, tax_rate, extra_vals in products:
        existing = _rpc(
            models,
            odoo_db,
            uid,
            odoo_pass,
            "product.template",
            "search_read",
            [[["default_code", "=", ref]]],
            {"fields": ["id"], "limit": 1},
        )

        tax_id = tax_map.get(tax_rate) or tax_map.get(0.0)
        vals: dict[str, Any] = {
            "name": name,
            "default_code": ref,
            "list_price": price,
            "type": "consu",
            "pos_categ_ids": [(6, 0, [pos_cat_id])],
            "available_in_pos": True,
        }
        if tax_id:
            vals["taxes_id"] = [[6, 0, [tax_id]]]
        vals.update(extra_vals)

        if existing:
            _rpc(models, odoo_db, uid, odoo_pass, "product.template", "write", [[existing[0]["id"]], vals])
        else:
            _rpc(models, odoo_db, uid, odoo_pass, "product.template", "create", [vals])


def load_demo_data(odoo_db: str, uid: int, odoo_pass: str, models: OdooModelsProxy) -> bool:
    """Seed a minimal set of demo partners and products for local development.

    Creates a demo partner ``John Doe (Demo)`` with ``x_user_id=demo-user-123``
    and a pre-loaded wallet balance of €50, plus standard drinks products.

    This function uses ``price_include=False`` taxes (different from production)
    so Odoo's own demo/test data can coexist. It is only called when
    ``ODOO_LOAD_DEMO_DATA=true`` is set in the environment.

    Idempotent: checks by ``x_user_id`` / ``default_code`` before creating.

    Returns:
        ``True`` always — individual product failures are caught and logged
        without aborting the rest of the seed.
    """
    print("Loading demo data...", flush=True)

    existing_partner = _rpc(
        models, odoo_db, uid, odoo_pass, "res.partner", "search",
        [[["x_user_id", "=", "demo-user-123"]]]
    )
    if not existing_partner:
        _rpc(models, odoo_db, uid, odoo_pass, "res.partner", "create", [{
            "name": "John Doe (Demo)",
            "email": "john.doe@example.com",
            "x_user_id": "demo-user-123",
            "x_badge_id": "DEMO-BADGE-001",
            "x_wallet_balance": 50.0,
        }])

    products = [
        ("Cola", "DRINK-001", 2.50, 21),
        ("Water", "DRINK-002", 1.80, 6),
        ("Coffee", "DRINK-003", 2.20, 6),
        ("Beer", "DRINK-004", 3.00, 21),
        ("Sandwich Cheese", "FOOD-001", 4.50, 6),
        ("Pasta Bolognaise", "FOOD-002", 8.50, 12),
    ]

    for name, ref, price, tax in products:
        try:
            existing = _rpc(
                models, odoo_db, uid, odoo_pass, "product.template", "search_read",
                [[["default_code", "=", ref]]], {"fields": ["id"], "limit": 1}
            )
            tax_ids = _rpc(
                models, odoo_db, uid, odoo_pass, "account.tax", "search",
                [
                    [["amount", "=", tax],
                     ["type_tax_use", "=", "sale"],
                     ["amount_type", "=", "percent"],
                     ["price_include", "=", False]]
                ]
            )
            tax_id = tax_ids[0] if tax_ids else False

            if not existing:
                _rpc(models, odoo_db, uid, odoo_pass, "product.template", "create", [{
                    "name": name,
                    "default_code": ref,
                    "list_price": price,
                    "type": "consu",
                    "taxes_id": [[6, 0, [tax_id]]] if tax_id else [],
                    "available_in_pos": True,
                }])
            else:
                _rpc(
                    models, odoo_db, uid, odoo_pass, "product.template", "write",
                    [[existing[0]["id"]]], {"list_price": price, "available_in_pos": True}
                )
        except Exception as exc:
            print(f"Could not create/update product '{name}': {exc}", flush=True)

    return True
