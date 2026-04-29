# odoo_setup.py — Odoo bootstrap helpers for the Kassa integration service
# Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026
#
# All functions are idempotent: safe to call on every container startup.
# Execution is orchestrated by main.py.

import time
import defusedxml.xmlrpc
from typing import Any

import requests
from typing_utils import OdooModelsProxy

defusedxml.xmlrpc.monkey_patch()


def _rpc(models: OdooModelsProxy, *args: Any, **kwargs: Any) -> Any:
    """
    Thin wrapper around ServerProxy.execute_kw() that returns Any.
    """
    return models.execute_kw(*args, **kwargs)


def wait_for_odoo(url: str, timeout: int = 60) -> bool:
    """
    Poll Odoo's web endpoint until it returns a 200 OK.

    The container might be "up" but Odoo takes time to initialize the database
    and load modules. Starting the integration service before Odoo is ready
    would lead to immediate connection failures.
    """
    start_time = time.time()
    print(f"⌛ Waiting for Odoo at {url}...", flush=True)

    while time.time() - start_time < timeout:
        try:
            # Check the /web/database/selector or root to see if service is alive
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print("✅ Odoo is reachable.", flush=True)
                return True
        except requests.exceptions.RequestException:
            pass

        time.sleep(2)

    print(f"❌ Odoo was not reachable within {timeout}s", flush=True)
    return False


def ensure_custom_fields(odoo_db: str, uid: int, odoo_pass: str, models: OdooModelsProxy) -> None:
    """
    Create custom x_ fields needed for CRM/IoT integration if they don't exist.

    Uses the ir.model.fields model to check for field names. All custom fields
    in Odoo MUST start with 'x_'.
    """
    print("🛠️  Checking custom fields...", flush=True)

    # (Model name, Field name, Field description, Field type)
    fields_to_check = [
        # Customer (res.partner) fields
        ("res.partner", "x_user_id", "External CRM User ID", "char"),
        ("res.partner", "x_badge_id", "IoT Badge ID", "char"),
        ("res.partner", "x_wallet_balance", "Visitor Wallet Balance", "float"),
        ("res.partner", "x_date_of_birth", "Date of Birth", "date"),
        # POS Order fields
        ("pos.order", "x_rabbitmq_sent", "Sent to CRM via RabbitMQ", "boolean"),
        ("pos.order", "x_wallet_updated", "Wallet Balance Adjusted", "boolean"),
        ("pos.order", "x_payment_message_id", "CRM Payment Correlation ID", "char"),
    ]

    for model, name, ttype, ftype in fields_to_check:
        existing = _rpc(models, odoo_db, uid, odoo_pass, "ir.model.fields", "search",
                        [[["model", "=", model], ["name", "=", name]]])

        if not existing:
            print(f"   Creating {model}.{name} ({ftype})...", flush=True)
            # Find the model ID first
            model_id = _rpc(models, odoo_db, uid, odoo_pass, "ir.model", "search",
                            [[["model", "=", model]]])[0]

            _rpc(models, odoo_db, uid, odoo_pass, "ir.model.fields", "create", {
                "name": name,
                "field_description": ttype,
                "model_id": model_id,
                "ttype": ftype,
                "state": "manual",  # 'manual' allows deletion/edit via UI and RPC
            })


def setup_payment_methods(odoo_db: str, uid: int, odoo_pass: str, models: OdooModelsProxy) -> None:
    """
    Ensure the "Badge Wallet" payment method exists in the POS.

    If missing, it creates the method and links it to the default POS journal.
    This allows visitors to "pay" using their badge balance.
    """
    print("🛠️  Checking payment methods...", flush=True)

    # Check if 'Badge Wallet' exists
    existing = _rpc(models, odoo_db, uid, odoo_pass, "pos.payment.method", "search",
                    [[["name", "=", "Badge Wallet"]]])

    if not existing:
        print("   Creating 'Badge Wallet' payment method...", flush=True)
        _rpc(models, odoo_db, uid, odoo_pass, "pos.payment.method", "create", {
            "name": "Badge Wallet",
            "is_cash_count": False,
            "split_transactions": True,
        })
    else:
        print("   'Badge Wallet' method exists.", flush=True)


def load_demo_data(odoo_db: str, uid: int, odoo_pass: str, models: OdooModelsProxy) -> None:
    """
    Populate Odoo with base products and a test customer for development.

    Idempotent: checks for product names/internal refs before creating.
    """
    print("🛠️  Loading demo data...", flush=True)

    # 1. Create a demo customer
    existing_partner = _rpc(models, odoo_db, uid, odoo_pass, "res.partner", "search",
                            [[["x_user_id", "=", "demo-user-123"]]])

    if not existing_partner:
        print("   Creating demo customer...", flush=True)
        _rpc(models, odoo_db, uid, odoo_pass, "res.partner", "create", {
            "name": "John Doe (Demo)",
            "email": "john.doe@example.com",
            "x_user_id": "demo-user-123",
            "x_badge_id": "DEMO-BADGE-001",
            "x_wallet_balance": 50.0,
        })

    # 2. Create base products (Food/Drink)
    products = [
        ("Cola", "DRINK-001", 2.50, 21),
        ("Water", "DRINK-002", 1.80, 6),
        ("Coffee", "DRINK-003", 2.20, 6),
        ("Beer", "DRINK-004", 3.00, 21),
        ("Sandwich Cheese", "FOOD-001", 4.50, 6),
        ("Pasta Bolognaise", "FOOD-002", 8.50, 12),
    ]

    try:
        for name, ref, price, tax in products:
            existing = _rpc(models, odoo_db, uid, odoo_pass, "product.template", "search_read",
                            [[["default_code", "=", ref]]], ["id"])

            if not existing:
                print(f"   Creating product: {name} ({ref})...", flush=True)

                # Get the tax ID (Odoo taxes are records)
                tax_id = _rpc(models, odoo_db, uid, odoo_pass, "account.tax", "search",
                              [[["amount", "=", tax], ["type_tax_use", "=", "sale"]]])

                _rpc(models, odoo_db, uid, odoo_pass, "product.template", "create", {
                    "name": name,
                    "default_code": ref,
                    "list_price": price,
                    "type": "consu",
                    "taxes_id": [[6, 0, tax_id]] if tax_id else [],
                    "available_in_pos": True,
                })
            else:
                # Update price if it changed
                update_vals = {"list_price": price, "available_in_pos": True}
                _rpc(models, odoo_db, uid, odoo_pass, "product.template", "write",
                     [[existing[0]["id"]], update_vals]
                     )

    except Exception as e:
        print(f"⚠️  Could not create demo products: {e}", flush=True)
