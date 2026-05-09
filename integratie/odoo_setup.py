# odoo_setup.py - Odoo bootstrap helpers for the Kassa integration service
# Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026

from __future__ import annotations

import time
import xmlrpc.client  # nosec
from typing import Any, cast

import defusedxml.xmlrpc
import requests

from typing_utils import OdooModelsProxy

defusedxml.xmlrpc.monkey_patch()


def _rpc(models: OdooModelsProxy, *args: Any, **kwargs: Any) -> Any:
    return models.execute_kw(*args, **kwargs)


def _extract_company_id(user_info: list[dict[str, Any]] | None) -> int | None:
    if not user_info:
        return None
    company = user_info[0].get("company_id")
    if isinstance(company, (list, tuple)) and company:
        return int(company[0])
    if isinstance(company, int):
        return company
    return None


def _common_and_models(odoo_url: str) -> tuple[Any, Any]:
    common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common", allow_none=True)
    models = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/object", allow_none=True)
    return common, models


def wait_for_odoo(url: str, timeout: int = 300) -> bool:
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
        print(f"Waiting for database '{odoo_db}' to become available...", flush=True)
        deadline = time.time() + 300
        uid = None
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
            time.sleep(5)

        print(f"Database '{odoo_db}' was not available after creation attempt.", flush=True)
        return False
    except Exception as e:
        print(f"Unexpected error in setup_database: {e}", flush=True)
        return False


def _ensure_custom_user(odoo_url: str, odoo_db: str, odoo_user: str, odoo_pass: str) -> None:
    """Ensure the custom Odoo user exists and has the correct password."""
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
        if not module_state or module_state[0].get("state") != "installed":
            _rpc(models, odoo_db, uid, odoo_pass, "ir.module.module",
                 "button_immediate_install", [[module_id]])
    return True


def ensure_custom_fields(odoo_url: str, odoo_db: str, odoo_user: str, odoo_pass: str) -> bool:
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
        ("res.partner", "x_date_of_birth", "Date of Birth", "date", {}),
        ("res.partner", "x_session_id", "Session ID", "char", {}),
        ("res.partner", "x_session_title", "Session Title", "char", {}),
        ("res.partner", "x_company_id", "Company ID", "char", {}),
        ("res.partner", "x_outstanding_amount", "Outstanding Amount", "float", {}),
        ("res.partner", "x_payment_status", "Payment Status", "char", {}),
        ("product.template", "x_is_topup", "Top-up Product", "boolean", {}),
        ("product.template", "x_age_restricted", "Age Restricted", "boolean", {}),
        ("pos.order", "x_rabbitmq_sent", "Sent to CRM via RabbitMQ", "boolean", {}),
        ("pos.order", "x_wallet_updated", "Wallet Balance Adjusted", "boolean", {}),
        ("pos.order", "x_payment_message_id", "CRM Payment Correlation ID", "char", {}),
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
        _rpc(
            models, odoo_db, uid, odoo_pass, "res.company", "write",
            [[company_id], {"tax_calculation_rounding_method": "round_per_line"}]
        )

    return tax_map


def ensure_pos_categories(odoo_url: str, odoo_db: str, odoo_user: str, odoo_pass: str) -> tuple[int, int, int]:
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
    reg_cat_id: int,
    tax_map: dict[float, int],
) -> None:
    common, models = _common_and_models(odoo_url)
    uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
    if not uid:
        return

    products: list[tuple[str, str, float, int, float, dict[str, Any]]] = [
        ("Top-up EUR 10", "TOPUP-010", 10.0, topup_cat_id, 0.0, {"x_is_topup": True}),
        ("Top-up EUR 20", "TOPUP-020", 20.0, topup_cat_id, 0.0, {"x_is_topup": True}),
        ("Cola", "DRINK-001", 2.50, drinks_cat_id, 21.0, {}),
        ("Water", "DRINK-002", 1.80, drinks_cat_id, 6.0, {}),
        ("Coffee", "DRINK-003", 2.20, drinks_cat_id, 6.0, {}),
        ("Beer", "DRINK-004", 3.00, drinks_cat_id, 21.0, {"x_age_restricted": True}),
        ("Inschrijving", "REG-001", 0.0, reg_cat_id, 0.0, {}),
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
