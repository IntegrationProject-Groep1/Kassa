# odoo_setup.py - Odoo bootstrap helpers for the Kassa integration service
# Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026

from __future__ import annotations

import time
import xmlrpc.client  # nosec
from typing import Any

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


def wait_for_odoo(url: str, timeout: int = 60) -> bool:
    print(f"Waiting for Odoo at {url}...", flush=True)
    attempts = max(1, timeout // 5)

    for _ in range(attempts):
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
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
    common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common", allow_none=True)

    try:
        uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
        if uid:
            return True
    except Exception:
        pass

    response = requests.post(
        f"{odoo_url}/web/database/create",
        data={
            'master_pwd': odoo_master_pass,
            'name': odoo_db,
            'login': odoo_user,
            'email': odoo_user,
            'password': odoo_pass,
            'phone': '',
            'lang': 'en_US',
            'country_code': 'be',
            'company_name': odoo_db,
            'demo': '1' if odoo_load_demo else '',
        },
        timeout=30,
    )
    if response.status_code >= 400:
        print(
            f"Database create request failed with HTTP {response.status_code}: {response.text[:300]}",
            flush=True,
        )
        return False

    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
            if uid:
                return True
        except Exception:
            pass
        time.sleep(2)

    print(f"Database '{odoo_db}' was not available after creation attempt.", flush=True)
    return False


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
    module_state = _rpc(models, odoo_db, uid, odoo_pass, "ir.module.module", "read", [[module_id]], {"fields": ["state"]})
    if module_state and module_state[0].get("state") == "installed":
        return True

    _rpc(models, odoo_db, uid, odoo_pass, "ir.module.module", "button_immediate_install", [[module_id]])
    deadline = time.time() + 60
    while time.time() < deadline:
        module_state = _rpc(models, odoo_db, uid, odoo_pass, "ir.module.module", "read", [[module_id]], {"fields": ["state"]})
        if module_state and module_state[0].get("state") == "installed":
            return True
        time.sleep(2)
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
        module_state = _rpc(models, odoo_db, uid, odoo_pass, "ir.module.module", "read", [[module_id]], {"fields": ["state"]})
        if not module_state or module_state[0].get("state") != "installed":
            _rpc(models, odoo_db, uid, odoo_pass, "ir.module.module", "button_immediate_install", [[module_id]])
    return True


def ensure_custom_fields(odoo_url: str, odoo_db: str, odoo_user: str, odoo_pass: str) -> bool:
    print("Checking custom fields...", flush=True)
    common, models = _common_and_models(odoo_url)
    uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
    if not uid:
        return False

    fields_to_check = [
        ("res.partner", "x_user_id", "External CRM User ID", "char", {"index": True}),
        ("res.partner", "x_badge_id", "IoT Badge ID", "char", {"index": True}),
        ("res.partner", "x_wallet_balance", "Visitor Wallet Balance", "float", {}),
        ("res.partner", "x_date_of_birth", "Date of Birth", "date", {}),
        ("product.template", "x_is_topup", "Top-up Product", "boolean", {}),
        ("product.template", "x_age_restricted", "Age Restricted", "boolean", {}),
        ("pos.order", "x_rabbitmq_sent", "Sent to CRM via RabbitMQ", "boolean", {}),
        ("pos.order", "x_wallet_updated", "Wallet Balance Adjusted", "boolean", {}),
        ("pos.order", "x_payment_message_id", "CRM Payment Correlation ID", "char", {}),
    ]

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
        _rpc(models, odoo_db, uid, odoo_pass, "ir.model.fields", "create", [create_vals])

    return True


def ensure_tax_settings(odoo_url: str, odoo_db: str, odoo_user: str, odoo_pass: str) -> dict[float, int]:
    common, models = _common_and_models(odoo_url)
    uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
    if not uid:
        return {}

    user_info = _rpc(models, odoo_db, uid, odoo_pass, "res.users", "read", [[uid]], {"fields": ["company_id"]})
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
            [[["amount", "=", rate], ["type_tax_use", "=", "sale"], ["amount_type", "=", "percent"], ["price_include", "=", False]]],
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
                "name": f"{int(rate)}% Sales Tax",
                "amount": rate,
                "amount_type": "percent",
                "type_tax_use": "sale",
                "price_include": False,
            }],
        )

    if company_id:
        _rpc(models, odoo_db, uid, odoo_pass, "res.company", "write", [[company_id], {"tax_calculation_rounding_method": "round_per_line"}])

    return tax_map


def ensure_pos_categories(odoo_url: str, odoo_db: str, odoo_user: str, odoo_pass: str) -> tuple[int, int]:
    common, models = _common_and_models(odoo_url)
    uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
    if not uid:
        return 0, 0

    def _ensure_category(name: str) -> int:
        records = _rpc(
            models,
            odoo_db,
            uid,
            odoo_pass,
            "pos.category",
            "search_read",
            [[["name", "=", name]]],
            {"fields": ["id"], "limit": 1},
        )
        if records:
            return records[0]["id"]
        return _rpc(models, odoo_db, uid, odoo_pass, "pos.category", "create", [{"name": name}])

    return _ensure_category("Top-ups"), _ensure_category("Drinks")


def ensure_payment_methods(odoo_url: str, odoo_db: str, odoo_user: str, odoo_pass: str) -> list[int]:
    common, models = _common_and_models(odoo_url)
    uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
    if not uid:
        return []

    user_info = _rpc(models, odoo_db, uid, odoo_pass, "res.users", "read", [[uid]], {"fields": ["company_id"]})
    company_id = _extract_company_id(user_info)

    def _ensure_method(name: str, is_cash_count: bool, extra_vals: dict[str, Any] | None = None) -> int:
        domain = [["name", "=", name]]
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
            return records[0]["id"]

        vals: dict[str, Any] = {"name": name, "is_cash_count": is_cash_count}
        if extra_vals:
            vals.update(extra_vals)
        if company_id is not None:
            vals["company_id"] = company_id
        return _rpc(models, odoo_db, uid, odoo_pass, "pos.payment.method", "create", [vals])

    return [
        _ensure_method("Cash", True),
        _ensure_method("Card", False),
        _ensure_method("Badge Wallet", False, {"split_transactions": True}),
    ]


def ensure_demo_products(
    odoo_url: str,
    odoo_db: str,
    odoo_user: str,
    odoo_pass: str,
    topup_cat_id: int,
    drinks_cat_id: int,
    tax_map: dict[float, int],
) -> None:
    common, models = _common_and_models(odoo_url)
    uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
    if not uid:
        return

    products = [
        ("Top-up EUR 10", "TOPUP-010", 10.0, topup_cat_id, 0.0, {"x_is_topup": True}),
        ("Top-up EUR 20", "TOPUP-020", 20.0, topup_cat_id, 0.0, {"x_is_topup": True}),
        ("Cola", "DRINK-001", 2.50, drinks_cat_id, 21.0, {}),
        ("Water", "DRINK-002", 1.80, drinks_cat_id, 6.0, {}),
        ("Coffee", "DRINK-003", 2.20, drinks_cat_id, 6.0, {}),
        ("Beer", "DRINK-004", 3.00, drinks_cat_id, 21.0, {"x_age_restricted": True}),
    ]

    for name, ref, price, categ_id, tax_rate, extra_vals in products:
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
            "categ_id": categ_id,
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

    existing_partner = _rpc(models, odoo_db, uid, odoo_pass, "res.partner", "search", [[ ["x_user_id", "=", "demo-user-123"] ]])
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
            existing = _rpc(models, odoo_db, uid, odoo_pass, "product.template", "search_read", [[ ["default_code", "=", ref] ]], {"fields": ["id"], "limit": 1})
            tax_ids = _rpc(models, odoo_db, uid, odoo_pass, "account.tax", "search", [[ ["amount", "=", tax], ["type_tax_use", "=", "sale"], ["amount_type", "=", "percent"], ["price_include", "=", False] ]])
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
                _rpc(models, odoo_db, uid, odoo_pass, "product.template", "write", [[existing[0]["id"]], {"list_price": price, "available_in_pos": True}])
        except Exception as exc:
            print(f"Could not create/update product '{name}': {exc}", flush=True)

    return True
