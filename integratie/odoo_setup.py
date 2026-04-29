# odoo_setup.py — Odoo bootstrap helpers for the Kassa integration service
# Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026
#
# All functions are idempotent: safe to call on every container startup.
# Execution order (managed by main.py):
#   1. wait_for_odoo          – wait for the Odoo web process
#   2. setup_database         – create the DB if it doesn't exist yet
#   3. ensure_pos_installed   – auto-install the point_of_sale module
#   3b. ensure_kassa_addons    – auto-install/upgrade kassa_pos_custom addon
#   4. ensure_custom_fields   – create x_* fields on res.partner / pos.order / product.template
#   5. ensure_tax_settings    – ensure Belgian VAT rates exist and are price-inclusive
#   6. ensure_pos_categories  – create "Top-ups" and "Drinks" POS categories
#   7. ensure_payment_methods – create Cash / Card / Badge Wallet payment methods
#   8. ensure_demo_products   – create demo products linked to the categories and taxes

import time
import xmlrpc.client  # nosec
import defusedxml.xmlrpc
defusedxml.xmlrpc.monkey_patch()
from typing import Any

import requests


def _rpc(models: xmlrpc.client.ServerProxy, *args: Any, **kwargs: Any) -> Any:
    """
    Thin wrapper around ServerProxy.execute_kw() that returns Any.

    xmlrpc.client has no typed stubs: every call returns _Marshallable
    (int | float | str | bytes | list | dict | None | ...).  Mypy cannot
    narrow that union when callers index or iterate the result, producing
    hundreds of false-positive errors.  Centralising the cast here means a
    single ignore comment instead of one per call site.
    """
    return models.execute_kw(*args, **kwargs)  # type: ignore[no-any-return]


def _extract_company_id(user_info: list) -> "int | None":
    """Safely extract company_id from a res.users.read result.

    Odoo returns many2one fields as [id, name] when set or False when unset.
    Indexing False raises TypeError, so we guard with isinstance.
    """
    raw = user_info[0].get("company_id") if user_info else None
    return raw[0] if isinstance(raw, (list, tuple)) else None


# ── Step 1: Wait for Odoo web server ─────────────────────────────────────────

def wait_for_odoo(odoo_url: str, timeout: int = 300) -> bool:
    """Wait until Odoo web server is responding (before DB exists)."""
    print("⏳ Waiting for Odoo to become available...", flush=True)
    for i in range(timeout // 5):
        try:
            resp = requests.get(f'{odoo_url}/web/database/selector', timeout=5)
            if resp.status_code < 500:
                print("✅ Odoo web server is up", flush=True)
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(5)
    print("⚠️  Odoo did not respond in time — continuing anyway", flush=True)
    return False


# ── Step 2: Database creation / readiness ─────────────────────────────────────

def setup_database(
    odoo_url: str,
    odoo_db: str,
    odoo_user: str,
    odoo_pass: str,
    odoo_master_pass: str,
    odoo_load_demo: bool = False,
) -> bool:
    """Auto-create the Odoo database if it doesn't exist yet, then wait until accessible."""
    common = xmlrpc.client.ServerProxy(f'{odoo_url}/xmlrpc/2/common', allow_none=True)

    # Fast path: DB already exists and is accessible
    try:
        uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
        if uid:
            print(f"[SETUP] Database '{odoo_db}' already exists and is accessible", flush=True)
            return True
        else:
            # uid == 0: DB responded but credentials are wrong for this DB
            print(f"[SETUP] Database '{odoo_db}' is up but authenticate() returned 0.", flush=True)
            print(f"  -> ODOO_USER='{odoo_user}' or ODOO_PASS may be wrong for this DB.", flush=True)
            print("  -> Will try DB creation in case the database does not exist yet.", flush=True)
    except Exception as e:
        print(f"[SETUP] Fast-path auth raised {type(e).__name__} "
              "-- DB may not exist yet, attempting creation.", flush=True)

    # Attempt to create the database
    print(f"[SETUP] Attempting to create database '{odoo_db}'...", flush=True)
    print(f"[SETUP] Demo data on create: {'enabled' if odoo_load_demo else 'disabled'}", flush=True)
    try:
        resp = requests.post(
            f'{odoo_url}/web/database/create',
            data={
                'master_pwd': odoo_master_pass,
                'name': odoo_db,
                'login': odoo_user,
                'password': odoo_pass,
                'lang': 'en_US',
                'country_code': 'be',
                'phone': '',
                'demo': '1' if odoo_load_demo else '',
            },
            timeout=120,
            allow_redirects=True
        )
        if resp.status_code in (200, 302):
            print("[SETUP] DB creation accepted -- waiting for Odoo to initialise", flush=True)
        elif resp.status_code == 403:
            print("[SETUP] DB creation returned 403 (Forbidden). Two possible causes:", flush=True)
            print("  1. Database already exists (normal on restart) -- this is fine.", flush=True)
            print("  2. ODOO_MASTER_PASS is wrong.", flush=True)
            print("  Continuing -- will poll for existing DB to become accessible.", flush=True)
        else:
            print(f"[SETUP] DB creation returned HTTP {resp.status_code} -- continuing.", flush=True)
    except Exception as e:
        print(f"[SETUP] DB creation HTTP request failed: {e}", flush=True)

    # Poll until the DB is accessible (fresh Odoo init can take several minutes)
    print("[SETUP] Polling until '" + odoo_db + "' is accessible (up to 10 min)...", flush=True)
    last_result = "not attempted yet"
    for attempt in range(120):
        time.sleep(5)
        try:
            uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
            if uid:
                print(
                    f"[SETUP] Database '{odoo_db}' is now accessible "
                    f"(after ~{(attempt + 1) * 5}s)",
                    flush=True,
                )
                return True
            last_result = (
                f"authenticate() returned 0 -- ODOO_USER='{odoo_user}' "
                "or ODOO_PASS rejected, or database does not exist"
            )
        except Exception as e:
            last_result = f"{type(e).__name__}: {e}"
        if (attempt + 1) % 6 == 0:
            print(f"[SETUP]   {(attempt + 1) * 5}s elapsed | {last_result}", flush=True)

    master_status = "<set>" if odoo_master_pass else "NOT SET -- likely the problem"
    print("[SETUP] Database not accessible after 10 minutes.", flush=True)
    print(f"  Last result : {last_result}", flush=True)
    print(f"  ODOO_URL    : {odoo_url}", flush=True)
    print(f"  ODOO_DB     : {odoo_db}", flush=True)
    print(f"  ODOO_USER   : {odoo_user}", flush=True)
    print(f"  ODOO_MASTER : {master_status}", flush=True)
    return False


# ── Step 3: POS module installation ───────────────────────────────────────────

def ensure_pos_installed(odoo_url: str, odoo_db: str, odoo_user: str, odoo_pass: str) -> bool:
    """
    Check if point_of_sale module is installed in Odoo.
    If not, install it automatically before starting the poller.
    """
    print("🔍 Checking if Point of Sale module is installed...", flush=True)

    try:
        common = xmlrpc.client.ServerProxy(f'{odoo_url}/xmlrpc/2/common', allow_none=True)
        uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
        if not uid:
            print("❌ Cannot check modules — Odoo auth failed", flush=True)
            return False

        models = xmlrpc.client.ServerProxy(f'{odoo_url}/xmlrpc/2/object', allow_none=True)

        module_ids = _rpc(models,
                          odoo_db, uid, odoo_pass,
                          'ir.module.module', 'search',
                          [[['name', '=', 'point_of_sale']]]
                          )

        if not module_ids:
            print("⚠️  point_of_sale module not found in registry", flush=True)
            return False

        module_info = _rpc(models,
                           odoo_db, uid, odoo_pass,
                           'ir.module.module', 'read',
                           [module_ids, ['name', 'state']]
                           )

        state = module_info[0]['state'] if module_info else 'unknown'

        if state == 'installed':
            print("✅ Point of Sale module already installed", flush=True)
            return True

        print(f"📦 Point of Sale module state: {state} — installing now...", flush=True)

        _rpc(models,
             odoo_db, uid, odoo_pass,
             'ir.module.module', 'button_immediate_install',
             [module_ids]
             )

        # Wait for installation to complete (up to 120 seconds)
        for attempt in range(24):
            time.sleep(5)
            module_info = _rpc(models,
                               odoo_db, uid, odoo_pass,
                               'ir.module.module', 'read',
                               [module_ids, ['state']]
                               )
            new_state = module_info[0]['state']
            print(f"   ⏳ Installing... ({(attempt + 1) * 5}s) state={new_state}", flush=True)
            if new_state == 'installed':
                print("✅ Point of Sale module installed successfully!", flush=True)
                return True

        print("⚠️  POS install timed out — continuing anyway", flush=True)
        return False

    except Exception as e:
        print(f"⚠️  Could not auto-install POS module: {e}", flush=True)
        return False


# ── Step 3b: Kassa custom addons ──────────────────────────────────────────────

# List of custom addons to install/upgrade on every startup.
_KASSA_ADDONS = ['kassa_pos_custom']


def ensure_kassa_addons(odoo_url: str, odoo_db: str, odoo_user: str, odoo_pass: str) -> bool:
    """
    Ensure kassa_pos_custom (and any future addons in _KASSA_ADDONS) are installed
    and up-to-date. Installs missing modules and upgrades already-installed ones.
    Safe to call on every container startup — idempotent.
    """
    print("🔍 Checking Kassa custom addons...", flush=True)
    try:
        common = xmlrpc.client.ServerProxy(f'{odoo_url}/xmlrpc/2/common', allow_none=True)
        uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
        if not uid:
            print("⚠️  Cannot check custom addons — Odoo auth failed", flush=True)
            return False

        models = xmlrpc.client.ServerProxy(f'{odoo_url}/xmlrpc/2/object', allow_none=True)

        for addon_name in _KASSA_ADDONS:
            module_ids = _rpc(
                models, odoo_db, uid, odoo_pass,
                'ir.module.module', 'search',
                [[["name", "=", addon_name]]]
            )

            if not module_ids:
                print(f"⚠️  Addon '{addon_name}' not found in registry — skipping", flush=True)
                continue

            module_info = _rpc(
                models, odoo_db, uid, odoo_pass,
                'ir.module.module', 'read',
                [module_ids, ['name', 'state']]
            )
            state = module_info[0]['state'] if module_info else 'unknown'

            if state == 'installed':
                # Upgrade to pick up new Python code / views
                print(f"   🔄 Upgrading '{addon_name}'...", flush=True)
                _rpc(models, odoo_db, uid, odoo_pass,
                     'ir.module.module', 'button_immediate_upgrade', [module_ids])
            elif state in ('uninstalled', 'to install'):
                print(f"   📦 Installing '{addon_name}'...", flush=True)
                _rpc(models, odoo_db, uid, odoo_pass,
                     'ir.module.module', 'button_immediate_install', [module_ids])
            else:
                print(f"   ⏳ Addon '{addon_name}' state={state} — skipping", flush=True)
                continue

            # Poll until installed (up to 120 s)
            for attempt in range(24):
                time.sleep(5)
                info = _rpc(models, odoo_db, uid, odoo_pass,
                            'ir.module.module', 'read', [module_ids, ['state']])
                new_state = info[0]['state']
                print(f"      ⏳ ({(attempt + 1) * 5}s) state={new_state}", flush=True)
                if new_state == 'installed':
                    print(f"   ✅ Addon '{addon_name}' ready", flush=True)
                    break
            else:
                print(f"   ⚠️  Addon '{addon_name}' did not finish in time — continuing", flush=True)

        print("✅ Kassa addons check complete", flush=True)
        return True

    except Exception as e:
        print(f"⚠️  Could not verify Kassa addons: {e}", flush=True)
        return False


# ── Step 4: Custom fields ──────────────────────────────────────────────────────

# Each value is a 3-tuple: (odoo_ttype, field_label, extra_vals_dict)
# x_user_id and x_badge_id have index=True — looked up on every incoming message.
# Note: x_age (computed from x_date_of_birth) is NOT created here — it is a
# display-only convenience field defined in tools/setup_odoo.py for developers.
# The runtime service uses x_date_of_birth directly and does not need x_age.
_CUSTOM_FIELDS: dict[str, dict[str, tuple[str, str, dict]]] = {
    "res.partner": {
        "x_user_id":        ("char",    "External User ID",             {"index": True}),
        "x_badge_id":       ("char",    "Badge ID",                     {"index": True}),
        "x_wallet_balance": ("float",   "Wallet Balance (EUR)",         {}),
        "x_date_of_birth":  ("date",    "Date of Birth",                {}),
    },
    "pos.order": {
        "x_rabbitmq_sent":      ("boolean", "Sent to RabbitMQ",             {}),
        "x_wallet_updated":     ("boolean", "Wallet Update Processed",      {}),
        "x_payment_message_id": ("char",    "Payment Message ID",           {}),
    },
    "product.template": {
        "x_is_topup":       ("boolean", "Is Top-up Product",            {}),
        "x_age_restricted": ("boolean", "Is Age Restricted (Alcohol)",  {}),
    },
}


def ensure_custom_fields(odoo_url: str, odoo_db: str, odoo_user: str, odoo_pass: str) -> bool:
    """
    Create custom fields on res.partner, pos.order, and product.template if they don't exist yet.
    Safe to call on every startup — skips fields that are already present.
    """
    print("🔍 Checking custom Odoo fields...", flush=True)
    try:
        common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
        if not uid:
            print("⚠️  Cannot verify custom fields — Odoo auth failed", flush=True)
            return False

        models = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/object", allow_none=True)
        created = 0

        for model_name, fields in _CUSTOM_FIELDS.items():
            model_rows = _rpc(models,
                              odoo_db, uid, odoo_pass,
                              "ir.model", "search_read",
                              [[["model", "=", model_name]]],
                              {"fields": ["id"], "limit": 1},
                              )
            if not model_rows:
                print(f"⚠️  Model '{model_name}' not found — skipping", flush=True)
                continue

            model_id = model_rows[0]["id"]
            existing = {
                r["name"] for r in _rpc(models,
                                        odoo_db, uid, odoo_pass,
                                        "ir.model.fields", "search_read",
                                        [[["model", "=", model_name], ["name", "in", list(fields)]]],
                                        {"fields": ["name"]},
                                        )
            }

            for fname, (ttype, label, extra) in fields.items():
                if fname in existing:
                    continue
                _rpc(models,
                     odoo_db, uid, odoo_pass,
                     "ir.model.fields", "create",
                     [{**{"model_id": model_id, "name": fname,
                          "field_description": label, "ttype": ttype, "store": True}, **extra}],
                     )
                print(f"   ✅ Created field {model_name}.{fname} ({ttype})", flush=True)
                created += 1

        if created:
            print(f"✅ Custom fields ready — {created} new field(s) created", flush=True)
        else:
            print("✅ Custom fields ready — all fields already present", flush=True)
        return True

    except Exception as e:
        print(f"⚠️  Could not verify/create custom fields: {type(e).__name__}", flush=True)
        return False


# ── Step 5: Tax settings ───────────────────────────────────────────────────────

VALID_VAT_RATES = {0.0, 6.0, 12.0, 21.0}
TARGET_VAT_RATE = 6.0


def ensure_tax_settings(odoo_url: str, odoo_db: str, odoo_user: str, odoo_pass: str) -> dict:
    """
    Ensure price-inclusive VAT taxes exist for standard Belgian rates (0%, 6%, 12%, 21%).
    Uses amount_type='percent' + price_include=True so list_price IS the final customer price.
    Also fixes POS products with invalid tax rates to 6%.
    Returns a dict mapping {rate: tax_id} for use in ensure_demo_products.
    """
    print("🔍 Checking tax settings and POS product rates...", flush=True)
    try:
        common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
        if not uid:
            print("⚠️  Cannot check tax settings — Odoo auth failed", flush=True)
            return {}

        models = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/object", allow_none=True)

        user_info = _rpc(models, odoo_db, uid, odoo_pass, "res.users", "read",
                         [[uid], ["company_id"]])
        company_id: int | None = _extract_company_id(user_info)

        tax_map_by_rate = {}
        for rate in VALID_VAT_RATES:
            domain = [["amount", "=", rate], ["type_tax_use", "in", ["sale", "all"]],
                      ["amount_type", "=", "percent"], ["price_include", "=", True]]
            if company_id:
                domain.append(["company_id", "=", company_id])
            inclusive = _rpc(models,
                             odoo_db, uid, odoo_pass,
                             "account.tax", "search_read",
                             [domain],
                             {"fields": ["id", "name"], "limit": 1}
                             )
            if inclusive:
                tax_id = inclusive[0]["id"]
            else:
                create_vals: dict = {"name": f"BTW {int(rate)}% incl.", "amount": rate,
                                     "type_tax_use": "sale", "amount_type": "percent",
                                     "price_include": True}
                if company_id:
                    create_vals["company_id"] = company_id
                tax_id = _rpc(models,
                              odoo_db, uid, odoo_pass,
                              "account.tax", "create",
                              [create_vals]
                              )
                print(f"   ✅ Created {rate}% inclusive tax (percent + price_include)", flush=True)

            tax_map_by_rate[rate] = tax_id

        target_tax_id = tax_map_by_rate[TARGET_VAT_RATE]

        # Set BTW 6% incl. as the default sales tax on the company
        if company_id:
            _rpc(models, odoo_db, uid, odoo_pass, "res.company", "write",
                 [[company_id], {"account_sale_tax_id": target_tax_id}])
            print(f"   ✅ Set default sales tax to BTW {TARGET_VAT_RATE}% incl.", flush=True)

        # Check all POS products for invalid tax rates
        product_ids = _rpc(models,
                           odoo_db, uid, odoo_pass,
                           "product.template", "search",
                           [[["available_in_pos", "=", True]]]
                           )
        if not product_ids:
            return tax_map_by_rate

        products = _rpc(models,
                        odoo_db, uid, odoo_pass,
                        "product.template", "read",
                        [product_ids, ["id", "name", "taxes_id"]]
                        )

        all_tax_ids = list({tid for p in products for tid in p.get("taxes_id", [])})
        tax_map = {}
        if all_tax_ids:
            taxes_data = _rpc(models,
                              odoo_db, uid, odoo_pass,
                              "account.tax", "read",
                              [all_tax_ids, ["amount"]]
                              )
            tax_map = {t["id"]: t["amount"] for t in taxes_data}

        to_fix_ids = []
        for product in products:
            tax_ids = product.get("taxes_id", [])
            if not tax_ids:
                continue  # Tax-free products are intentional — leave them alone
            rates = {float(tax_map.get(tid, -1)) for tid in tax_ids}
            if not rates.issubset(VALID_VAT_RATES):
                print(f"   Fixing '{product['name']}': {rates} → {TARGET_VAT_RATE}%", flush=True)
                to_fix_ids.append(product["id"])

        if to_fix_ids:
            _rpc(models,
                 odoo_db, uid, odoo_pass,
                 "product.template", "write",
                 [to_fix_ids, {"taxes_id": [(6, 0, [target_tax_id])]}]
                 )
            print(
                f"✅ Product taxes ready — {len(to_fix_ids)} product(s) updated to {TARGET_VAT_RATE}%",
                flush=True,
            )
        else:
            print("✅ Product taxes ready — all products already have valid rates", flush=True)

        return tax_map_by_rate

    except Exception as e:
        print(f"⚠️  Could not verify/fix tax settings: {type(e).__name__}: {str(e)[:200]}", flush=True)
    return {}


# ── Step 6: POS categories ────────────────────────────────────────────────────

def ensure_pos_categories(
    odoo_url: str, odoo_db: str, odoo_user: str, odoo_pass: str
) -> tuple[int | None, int | None]:
    """Create (or confirm) the 'Top-ups' and 'Drinks' POS categories. Returns (topup_id, drinks_id)."""
    print("🔍 Checking POS categories...", flush=True)
    try:
        common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
        models = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/object", allow_none=True)

        def get_or_create_category(name: str) -> int:
            existing = _rpc(models,
                            odoo_db, uid, odoo_pass, "pos.category", "search_read",
                            [[["name", "=", name]]], {"fields": ["id"]}
                            )
            if not existing:
                cat_id = _rpc(models,
                              odoo_db, uid, odoo_pass, "pos.category", "create",
                              [{"name": name}]
                              )
                print(f"   ✅ Created POS category '{name}'", flush=True)
                return cat_id
            return existing[0]["id"]

        topup_cat_id = get_or_create_category("Top-ups")
        drinks_cat_id = get_or_create_category("Drinks")
        return topup_cat_id, drinks_cat_id

    except Exception as e:
        print(f"⚠️  Could not verify POS categories: {e}", flush=True)
        return None, None


# ── Step 7: Payment methods ───────────────────────────────────────────────────

def ensure_payment_methods(
    odoo_url: str, odoo_db: str, odoo_user: str, odoo_pass: str
) -> list:
    """Create Cash / Card / Badge Wallet payment methods if missing. Returns list of IDs."""
    print("🔍 Checking POS payment methods...", flush=True)
    try:
        common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
        models = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/object", allow_none=True)

        user_info = _rpc(models, odoo_db, uid, odoo_pass, "res.users", "read",
                         [[uid], ["company_id"]])
        company_id: int | None = _extract_company_id(user_info)

        needed = [
            {"name": "Cash",         "is_cash_count": True},
            {"name": "Card",         "is_cash_count": False},
            {"name": "Badge Wallet", "is_cash_count": False},
        ]

        method_ids = []
        for method in needed:
            domain = [["name", "=", method["name"]]]
            if company_id:
                domain.append(["company_id", "=", company_id])
            existing = _rpc(models,
                            odoo_db, uid, odoo_pass,
                            "pos.payment.method", "search_read",
                            [domain],
                            {"fields": ["id"]}
                            )
            if existing:
                method_ids.append(existing[0]["id"])
            else:
                create_vals: dict = {"name": method["name"], "is_cash_count": method["is_cash_count"]}
                if company_id:
                    create_vals["company_id"] = company_id
                pm_id = _rpc(models,
                             odoo_db, uid, odoo_pass,
                             "pos.payment.method", "create",
                             [create_vals]
                             )
                print(f"   ✅ Created payment method: {method['name']}", flush=True)
                method_ids.append(pm_id)

        return method_ids

    except Exception as e:
        print(f"⚠️  Could not verify payment methods: {e}", flush=True)
        return []


# ── Step 8: Demo products ─────────────────────────────────────────────────────

def ensure_demo_products(
    odoo_url: str,
    odoo_db: str,
    odoo_user: str,
    odoo_pass: str,
    topup_cat_id,
    drinks_cat_id,
    tax_map: dict | None = None,
) -> None:
    """Create demo products (Cola, Koffie, Pintje, Top-up €10/€20) if they don't exist yet."""
    print("🔍 Checking demo products...", flush=True)
    try:
        common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})
        models = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/object", allow_none=True)

        def get_tax_id(rate: float):
            t = _rpc(models,
                     odoo_db, uid, odoo_pass, "account.tax", "search_read",
                     [[["amount", "=", rate], ["type_tax_use", "in", ["sale", "all"]],
                       ["amount_type", "=", "percent"],
                         ["price_include", "=", True]]],
                     {"fields": ["id"], "limit": 1}
                     )
            return t[0]["id"] if t else None

        tax_0 = tax_map.get(0.0) if tax_map else get_tax_id(0.0)
        tax_6 = tax_map.get(6.0) if tax_map else get_tax_id(6.0)
        tax_21 = tax_map.get(21.0) if tax_map else get_tax_id(21.0)

        # list_price IS the final customer price (tax included)
        demo_products = [
            {
                "name": "Cola", "list_price": 2.50,
                "taxes_id": [(6, 0, [tax_6])] if tax_6 else [],
                "available_in_pos": True, "type": "consu",
                "pos_categ_ids": [(6, 0, [drinks_cat_id])] if drinks_cat_id else [],
            },
            {
                "name": "Koffie", "list_price": 2.80,
                "taxes_id": [(6, 0, [tax_6])] if tax_6 else [],
                "available_in_pos": True, "type": "consu",
                "pos_categ_ids": [(6, 0, [drinks_cat_id])] if drinks_cat_id else [],
            },
            {
                "name": "Pintje", "list_price": 3.00,
                "taxes_id": [(6, 0, [tax_21])] if tax_21 else [],
                "available_in_pos": True, "type": "consu", "x_age_restricted": True,
                "pos_categ_ids": [(6, 0, [drinks_cat_id])] if drinks_cat_id else [],
            },
            {
                "name": "Top-up €10", "list_price": 10.00,
                "taxes_id": [(6, 0, [tax_0])] if tax_0 else [],
                "available_in_pos": True, "type": "service", "x_is_topup": True,
                "pos_categ_ids": [(6, 0, [topup_cat_id])] if topup_cat_id else [],
            },
            {
                "name": "Top-up €20", "list_price": 20.00,
                "taxes_id": [(6, 0, [tax_0])] if tax_0 else [],
                "available_in_pos": True, "type": "service", "x_is_topup": True,
                "pos_categ_ids": [(6, 0, [topup_cat_id])] if topup_cat_id else [],
            },
        ]

        for product in demo_products:
            existing = _rpc(models,
                            odoo_db, uid, odoo_pass,
                            "product.template", "search_read",
                            [[["name", "=", product["name"]]]],
                            {"fields": ["id"]}
                            )
            if not existing:
                _rpc(models,
                     odoo_db, uid, odoo_pass,
                     "product.template", "create",
                     [product]
                     )
                print(f"   ✅ Created demo product: {product['name']}", flush=True)
            else:
                update_vals: dict = {
                    "image_1920": False,
                    "pos_categ_ids": product["pos_categ_ids"],
                }
                if product.get("taxes_id"):
                    update_vals["taxes_id"] = product["taxes_id"]
                _rpc(models,
                     odoo_db, uid, odoo_pass, "product.template", "write",
                     [[existing[0]["id"]], update_vals]
                     )

    except Exception as e:
        print(f"⚠️  Could not create demo products: {e}", flush=True)
