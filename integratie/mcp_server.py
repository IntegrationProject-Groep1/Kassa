"""
Kassa MCP Server — exposes Odoo 17 POS data as MCP tools.

Standalone process. Run with:
    python kassa_mcp_server.py

Requires env vars: ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASS
Optional: PORT (default 8004)
"""
import logging
import logging.handlers
import os
import xmlrpc.client  # nosec B411
from typing import Annotated, Any, cast

import defusedxml.xmlrpc
from dotenv import load_dotenv
from fastmcp import FastMCP
from pydantic import Field
from monitoring import monitor

_log = logging.getLogger("kassa-mcp")
if not _log.handlers:
    _log.setLevel(logging.DEBUG)
    _fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
    _sh = logging.StreamHandler(); _sh.setFormatter(_fmt); _log.addHandler(_sh)
    if os.path.isdir("/data"):
        _fh = logging.handlers.RotatingFileHandler("/data/kassa-mcp.log", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
        _fh.setFormatter(_fmt); _log.addHandler(_fh)
    _log.propagate = False

defusedxml.xmlrpc.monkey_patch()
load_dotenv()

mcp = FastMCP("kassa")

_URL = os.getenv("ODOO_URL", "")
_DB = os.getenv("ODOO_DB", "")
_USER = os.getenv("ODOO_USER", "")
_PASSWORD = os.getenv("ODOO_PASS", "")

_uid: int | None = None


def _get_uid() -> int:
    """Return the cached Odoo UID, authenticating if not yet done.

    Odoo XML-RPC is stateless — each execute_kw call requires the UID. We cache
    it after the first authenticate() call so MCP tool calls don't re-authenticate
    on every invocation. The UID is stable for the lifetime of the process unless
    Odoo revokes the session (handled by _odoo clearing _uid on Access Denied).
    """
    global _uid
    if _uid is None:
        common = xmlrpc.client.ServerProxy(f"{_URL}/xmlrpc/2/common")
        _uid = cast(int, common.authenticate(_DB, _USER, _PASSWORD, {}))
        if not _uid:
            raise RuntimeError("Odoo authentication failed — check ODOO_USER / ODOO_PASS")
    return _uid


def _odoo(model: str, method: str, args: list, kwargs: dict | None = None) -> Any:
    """Execute an Odoo XML-RPC call and return the raw result.

    Central wrapper so all MCP tools share a single connection configuration.
    Clears the cached UID on Access Denied so the next call re-authenticates —
    Odoo may invalidate sessions after a restart or password change.
    """
    global _uid
    models = xmlrpc.client.ServerProxy(f"{_URL}/xmlrpc/2/object")
    try:
        return models.execute_kw(_DB, _get_uid(), _PASSWORD, model, method, args, kwargs or {})
    except xmlrpc.client.Fault as exc:
        if "Access Denied" in str(exc):
            _uid = None
        raise


@mcp.tool()
def get_sales_summary(
    date_from: Annotated[
        str | None,
        Field(description="Start date filter in ISO format 'YYYY-MM-DD', e.g. '2026-05-01'. Omit for all time."),
    ] = None,
    date_to: Annotated[
        str | None,
        Field(description="End date filter in ISO format 'YYYY-MM-DD', e.g. '2026-05-31'. Omit for all time."),
    ] = None,
) -> dict[str, Any]:
    """
    Get a POS sales revenue summary.
    Returns total revenue, order count, and a breakdown by day.

    Authoritative for on-site POS revenue during an event (real-time Odoo).
    NOT for invoiced/accounting revenue — use `facturatie__get_revenue_summary` instead.
    """
    domain: list = [["state", "in", ["paid", "done", "invoiced"]]]
    if date_from:
        domain.append(["date_order", ">=", f"{date_from} 00:00:00"])
    if date_to:
        domain.append(["date_order", "<=", f"{date_to} 23:59:59"])

    try:
        orders = _odoo("pos.order", "search_read", [domain], {
            "fields": ["name", "amount_total", "date_order", "state"],
            "limit": 5000,
        })
        total_revenue = sum(o["amount_total"] for o in orders)
        by_day: dict[str, float] = {}
        for o in orders:
            day = o["date_order"][:10]
            by_day[day] = round(by_day.get(day, 0) + o["amount_total"], 2)
        _limit = 5000
        return {
            "total_revenue": round(total_revenue, 2),
            "order_count": len(orders),
            "currency": "EUR",
            "period": {"from": date_from, "to": date_to},
            "by_day": [{"date": d, "revenue": r} for d, r in sorted(by_day.items())],
            "truncated": len(orders) >= _limit,
        }
    except Exception as exc:
        return {"error": f"Odoo unavailable: {exc}", "total_revenue": 0, "order_count": 0}


@mcp.tool()
def get_recent_orders(
    limit: Annotated[int, Field(description="Max orders to return (default 20, max 100).")] = 20,
) -> dict[str, Any]:
    """
    Get the most recent POS orders.
    Includes customer name, master_uuid, wallet balance, date, total.

    POS orders only (live on-site sales). Wallet balance is LIVE Odoo value, not CRM cache.
    """
    limit = min(limit, 100)
    try:
        orders = _odoo(
            "pos.order", "search_read",
            [[["state", "in", ["paid", "done", "invoiced"]]]],
            {
                "fields": ["name", "amount_total", "date_order", "state", "partner_id"],
                "limit": limit,
                "order": "date_order desc",
            },
        )

        partner_ids = [o["partner_id"][0] for o in orders if o.get("partner_id")]
        partner_map: dict[int, dict] = {}
        if partner_ids:
            partners = _odoo(
                "res.partner", "read",
                [list(set(partner_ids))],
                {"fields": ["id", "name", "x_user_id", "x_wallet_balance", "x_badge_id"]},
            )
            partner_map = {p["id"]: p for p in partners}

        result = []
        for o in orders:
            if o.get("partner_id"):
                p = partner_map.get(o["partner_id"][0], {})
                partner_info = {
                    "customer": p.get("name") or o["partner_id"][1],
                    "master_uuid": p.get("x_user_id") or None,
                    "wallet_balance": p.get("x_wallet_balance", 0),
                    "badge_id": p.get("x_badge_id") or None,
                }
            else:
                partner_info = {"customer": None, "master_uuid": None, "wallet_balance": 0, "badge_id": None}

            result.append({
                "order_id": o["name"],
                "total": o["amount_total"],
                "date": o["date_order"],
                "status": o["state"],
                **partner_info,
            })

        return {"orders": result, "count": len(result)}
    except Exception as exc:
        return {"error": f"Odoo unavailable: {exc}", "orders": [], "count": 0}


@mcp.tool()
def get_all_wallets() -> dict[str, Any]:
    """
    Get all active wallet balances.
    Returns customers with a positive wallet balance, ordered by balance descending.
    Uses the custom x_wallet_balance field on res.partner.

    Returns live Odoo wallet balances. Authoritative ONLY for members whose CRM
    Wallet_Status__c='Leased'. For members not on lease, the CRM value
    (`crm__get_member_wallet`) is the source of truth.
    """
    try:
        partners = _odoo(
            "res.partner", "search_read",
            [[["x_wallet_balance", ">", 0]]],
            {
                "fields": [
                    "name", "x_user_id", "x_badge_id",
                    "x_wallet_balance", "x_pending_topup_balance",
                    "x_outstanding_amount", "x_payment_status",
                ],
                "limit": 200,
                "order": "x_wallet_balance desc",
            },
        )
        total_balance = sum(p.get("x_wallet_balance", 0) for p in partners)
        wallets = [
            {
                "customer": p["name"],
                "master_uuid": p.get("x_user_id") or None,
                "badge_id": p.get("x_badge_id") or None,
                "balance": p.get("x_wallet_balance", 0),
                "pending_topup": p.get("x_pending_topup_balance", 0),
                "outstanding_amount": p.get("x_outstanding_amount", 0),
                "payment_status": p.get("x_payment_status") or None,
            }
            for p in partners
        ]
        _limit = 200
        return {
            "wallets": wallets,
            "count": len(wallets),
            "total_balance": round(total_balance, 2),
            "currency": "EUR",
            "truncated": len(partners) >= _limit,
        }
    except Exception as exc:
        return {"error": f"Odoo unavailable: {exc}", "wallets": [], "count": 0}


@mcp.tool()
def get_wallet_by_master_uuid(
    master_uuid: Annotated[
        str,
        Field(description=(
            "The member's Master_UUID__c from CRM "
            "(format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx). "
            "Get it via crm__search_members or crm__list_members — never guess."
        )),
    ],
) -> dict[str, Any]:
    """
    Get the LIVE wallet balance for a member by their Master UUID.

    Call this whenever crm__get_member_wallet returns Wallet_Status__c='Leased'
    — during a lease Kassa holds the source-of-truth balance, not CRM.
    Returns: wallet_balance, pending_topup, outstanding_amount, payment_status.
    """
    if not master_uuid:
        return {"error": "master_uuid is required", "found": False}
    try:
        partners = _odoo(
            "res.partner", "search_read",
            [[["x_user_id", "=", master_uuid]]],
            {
                "fields": [
                    "id", "name", "x_user_id", "x_badge_id",
                    "x_wallet_balance", "x_pending_topup_balance",
                    "x_outstanding_amount", "x_payment_status",
                ],
                "limit": 1,
            },
        )
        if not partners:
            return {"error": f"No Odoo partner found with master_uuid '{master_uuid}'", "found": False}
        p = partners[0]
        return {
            "found": True,
            "customer": p.get("name"),
            "master_uuid": p.get("x_user_id") or None,
            "badge_id": p.get("x_badge_id") or None,
            "wallet_balance": float(p.get("x_wallet_balance") or 0.0),
            "pending_topup": float(p.get("x_pending_topup_balance") or 0.0),
            "outstanding_amount": float(p.get("x_outstanding_amount") or 0.0),
            "payment_status": p.get("x_payment_status") or None,
            "currency": "EUR",
            "source": "kassa_live",
        }
    except Exception as exc:
        return {"error": f"Odoo unavailable: {exc}", "found": False}


@mcp.tool()
def get_orders_by_email(
    email: Annotated[str, Field(description="The customer's email address (must include @). Exact match in Odoo.")],
    limit: Annotated[int, Field(description="Max orders to return (default 50, max 200).")] = 50,
) -> dict[str, Any]:
    """
    Get POS orders for a member identified by their email address.
    Looks up the Odoo partner by email then returns their full purchase history at the event (date, total, status).
    Use when an admin asks 'what did [person] buy at the kassa?' or needs to locate an order for a refund.
    """
    if not email or "@" not in email:
        return {"error": "A valid email address is required.", "orders": [], "count": 0}
    limit = min(limit, 200)
    try:
        partners = _odoo(
            "res.partner", "search_read",
            [[["email", "=ilike", email]]],
            {"fields": ["id", "name", "x_user_id"], "limit": 1},
        )
        if not partners:
            return {"error": f"No Odoo partner found with email '{email}'", "orders": [], "count": 0}
        partner = partners[0]
        orders = _odoo(
            "pos.order", "search_read",
            [[["partner_id", "=", partner["id"]], ["state", "in", ["paid", "done", "invoiced"]]]],
            {
                "fields": ["name", "amount_total", "date_order", "state"],
                "limit": limit,
                "order": "date_order desc",
            },
        )
        return {
            "customer": partner.get("name"),
            "master_uuid": partner.get("x_user_id") or None,
            "email": email,
            "orders": [
                {
                    "order_id": o["name"], "total": float(o.get("amount_total") or 0.0),
                    "date": o["date_order"], "status": o["state"],
                }
                for o in orders
            ],
            "count": len(orders),
            "truncated": len(orders) >= limit,
            "currency": "EUR",
        }
    except Exception as exc:
        return {"error": f"Odoo unavailable: {exc}", "orders": [], "count": 0}


@mcp.tool()
def get_orders_by_date_range(
    date_from: Annotated[str, Field(description="Start date in ISO format 'YYYY-MM-DD', e.g. '2026-05-01'.")],
    date_to: Annotated[str, Field(description="End date in ISO format 'YYYY-MM-DD', e.g. '2026-05-31'.")],
    limit: Annotated[int, Field(description="Max orders to return (default 100, max 500).")] = 100,
) -> dict[str, Any]:
    """
    Get POS orders placed within a date range.
    Useful for 'orders today', 'orders this week', or any specific period.
    Returns order list, total count, and total revenue for the period.
    """
    limit = min(limit, 500)
    domain = [
        ["state", "in", ["paid", "done", "invoiced"]],
        ["date_order", ">=", f"{date_from} 00:00:00"],
        ["date_order", "<=", f"{date_to} 23:59:59"],
    ]
    try:
        # Aggregate the true period total server-side before applying the row limit,
        # so total_revenue is always accurate even when results are truncated.
        stats = _odoo("pos.order", "read_group", [domain, ["amount_total"], []], {})
        total_revenue = round(stats[0].get("amount_total") or 0, 2) if stats else 0.0
        total_count = stats[0].get("__count", 0) if stats else 0

        orders = _odoo("pos.order", "search_read", [domain], {
            "fields": ["name", "amount_total", "date_order", "state", "partner_id"],
            "limit": limit,
            "order": "date_order desc",
        })
        partner_ids = [o["partner_id"][0] for o in orders if o.get("partner_id")]
        partner_map: dict[int, dict] = {}
        if partner_ids:
            partners = _odoo("res.partner", "read", [list(set(partner_ids))],
                             {"fields": ["id", "name", "x_user_id"]})
            partner_map = {p["id"]: p for p in partners}

        result = []
        for o in orders:
            partner = partner_map.get((o.get("partner_id") or [None])[0], {}) if o.get("partner_id") else {}
            result.append({
                "order_id":    o["name"],
                "total":       float(o.get("amount_total") or 0),
                "date":        o["date_order"],
                "status":      o["state"],
                "customer":    partner.get("name") or (o["partner_id"][1] if o.get("partner_id") else None),
                "master_uuid": partner.get("x_user_id") or None,
            })

        return {
            "orders":        result,
            "count":         len(result),
            "total_count":   total_count,
            "total_revenue": total_revenue,
            "currency":      "EUR",
            "period":        {"from": date_from, "to": date_to},
            "truncated":     len(orders) >= limit,
        }
    except Exception as exc:
        return {"error": f"Odoo unavailable: {exc}", "orders": [], "count": 0}


@mcp.tool()
def get_top_spenders(
    limit: Annotated[int, Field(description="Number of top spenders to return (default 10, max 50).")] = 10,
    date_from: Annotated[str | None, Field(description="Optional start date 'YYYY-MM-DD'. Omit for all time.")] = None,
    date_to: Annotated[str | None, Field(description="Optional end date 'YYYY-MM-DD'. Omit for all time.")] = None,
) -> dict[str, Any]:
    """
    Get the customers who have spent the most at the POS, ranked by total spend.
    Optionally scoped to a date range. Useful for VIP identification or event analysis.
    """
    limit = min(limit, 50)
    domain: list = [["state", "in", ["paid", "done", "invoiced"]], ["partner_id", "!=", False]]
    if date_from:
        domain.append(["date_order", ">=", f"{date_from} 00:00:00"])
    if date_to:
        domain.append(["date_order", "<=", f"{date_to} 23:59:59"])
    try:
        # Use read_group for server-side aggregation — avoids the 5000-row cap
        # and lets Odoo do the sorting, so results are always correct regardless
        # of total order volume.
        groups = _odoo("pos.order", "read_group",
                       [domain, ["amount_total"], ["partner_id"]],
                       {"orderby": "amount_total desc", "limit": limit})

        partner_ids = [g["partner_id"][0] for g in groups if g.get("partner_id")]
        partner_map: dict[int, dict] = {}
        if partner_ids:
            partners = _odoo("res.partner", "read", [partner_ids],
                             {"fields": ["id", "x_user_id", "x_badge_id"]})
            partner_map = {p["id"]: p for p in partners}

        ranked = []
        for g in groups:
            if not g.get("partner_id"):
                continue
            pid, name = g["partner_id"]
            extra = partner_map.get(pid, {})
            ranked.append({
                "partner_id":  pid,
                "name":        name,
                "total":       round(float(g.get("amount_total") or 0), 2),
                "order_count": g.get("__count") or 0,
                "master_uuid": extra.get("x_user_id") or None,
                "badge_id":    extra.get("x_badge_id") or None,
            })

        return {
            "top_spenders": ranked,
            "count":        len(ranked),
            "currency":     "EUR",
            "period":       {"from": date_from, "to": date_to},
        }
    except Exception as exc:
        return {"error": f"Odoo unavailable: {exc}", "top_spenders": [], "count": 0}


@mcp.tool()
def process_refund(
    order_id: Annotated[
        str,
        Field(description=(
            "The order name/reference from Odoo (e.g. 'POS/2026/0042'). "
            "Get it via get_recent_orders or get_orders_by_email — never guess."
        )),
    ],
    reason: Annotated[
        str,
        Field(description="Written reason for the refund (required). Example: 'Customer request — duplicate order'."),
    ],
) -> dict[str, Any]:
    """
    Issue a refund for a POS order in Odoo. WRITE OPERATION — confirm with admin before calling.

    Requires a written reason. Get the order_id via get_orders_by_email or get_recent_orders first —
    never guess the reference.
    Returns success status and the refund result from Odoo.
    """
    if not reason or not reason.strip():
        return {"error": "A reason is required to process a refund.", "success": False}
    _log.info("process_refund called: order_id=%s reason=%.100s", order_id, reason)
    try:
        ids = _odoo("pos.order", "search", [[["name", "=", order_id]]])
        if not ids:
            _log.warning("process_refund: order not found: %s", order_id)
            return {"error": f"Order '{order_id}' not found.", "success": False}
        result = _odoo("pos.order", "refund", [ids])
        monitor.log("info", "refund", f"Admin initiated refund for order {order_id}: {reason[:200]}")
        _log.info("process_refund success: order_id=%s", order_id)
        return {
            "success": True,
            "order_id": order_id,
            "reason": reason,
            "refund_result": result,
            "message": f"Refund initiated for order {order_id}.",
        }
    except Exception as exc:
        monitor.log("error", "refund", f"Admin refund failed for order {order_id}: {str(exc)[:300]}")
        _log.error("process_refund error: order_id=%s error=%s", order_id, exc)
        return {"error": f"Refund failed: {exc}", "success": False}


@mcp.tool()
def topup_wallet(
    master_uuid: Annotated[
        str,
        Field(description="CRM Master_UUID__c of the member. Get it via crm__search_members — never guess."),
    ],
    amount: Annotated[
        float,
        Field(description="Amount in EUR to add to the wallet. Must be positive.", gt=0),
    ],
    reason: Annotated[
        str,
        Field(description="Written reason for the top-up (required). Example: 'Admin adjustment — sponsor credit'."),
    ],
) -> dict[str, Any]:
    """
    Add funds to a member's live wallet in Odoo. WRITE OPERATION — confirm with admin before calling.

    Only use this when the wallet is Leased (CRM Wallet_Status__c='Leased') — otherwise
    the balance is owned by CRM and Odoo is not the source of truth.
    """
    import sender  # lazy: requires RABBIT_* env vars — fail before any Odoo writes
    if not reason or not reason.strip():
        return {"error": "A reason is required for a wallet top-up.", "success": False}
    _log.info("topup_wallet called: master_uuid=%s amount=%.2f reason=%.100s", master_uuid, amount, reason)
    try:
        partners = _odoo(
            "res.partner", "search_read",
            [[["x_user_id", "=", master_uuid]]],
            {
                "fields": [
                    "id", "name", "x_wallet_balance",
                    "x_outstanding_amount", "x_payment_status",
                    "x_lease_active",
                ],
                "limit": 1,
            },
        )
        if not partners:
            return {"error": f"No Odoo partner found for master_uuid '{master_uuid}'.", "success": False}
        partner = partners[0]
        partner_id = partner["id"]

        # Issue 3: Enforce lease-active guard — Odoo is only the source of truth while leased.
        # Without this check an admin top-up on an unleased wallet is silently overwritten
        # when CRM next pushes its authoritative balance via wallet_lease_grant.
        if not partner.get("x_lease_active"):
            return {
                "error": (
                    f"Wallet for '{partner['name']}' is not currently leased "
                    "(CRM Wallet_Status__c != 'Leased'). "
                    "Odoo is not the source of truth for this wallet — top-up rejected "
                    "to prevent silent balance corruption."
                ),
                "success": False,
            }

        old_balance = float(partner.get("x_wallet_balance") or 0)

        # Atomic SQL increment — no read-modify-write race
        new_balance_raw = _odoo("pos.order", "action_add_wallet_amount", [partner_id, amount])

        # action_add_wallet_amount returns False when the Odoo write fails.
        # Falling back to 0 would broadcast a zero balance to CRM/Frontend,
        # effectively wiping the wallet on all external systems — abort instead.
        if new_balance_raw is False:
            return {
                "error": "Wallet top-up failed in Odoo (action_add_wallet_amount returned False).",
                "success": False,
            }
        new_balance = float(new_balance_raw)

        _odoo("pos.order", "action_increment_lease_tx_count", [partner_id])

        # Issue 2: Publish wallet_balance_update to kassa.exchange so external systems
        # (CRM, Frontend) are informed of this admin-initiated top-up.
        # Mirrors the pattern used in receiver.py:process_wallet_remote_topup.
        wallet_xml = sender.build_wallet_balance_update_xml(
            identity_uuid=master_uuid,
            new_balance=new_balance,
            authority="kassa",
            status="active",
        )
        sender.send_typed_message("wallet_balance_update", wallet_xml)

        # Re-read partner after the balance update so the bus event reflects the
        # current x_outstanding_amount and x_payment_status, not the pre-topup values.
        fresh = _odoo("res.partner", "search_read",
                      [[["id", "=", partner_id]]],
                      {"fields": ["x_outstanding_amount", "x_payment_status", "name"], "limit": 1})
        fresh_partner = fresh[0] if fresh else partner

        # Notify all open POS sessions so the cashier sees the updated balance immediately
        _odoo("pos.order", "send_partner_bus_event", [
            partner_id,
            float(fresh_partner.get("x_outstanding_amount") or 0.0),
            fresh_partner.get("x_payment_status") or "unpaid",
            fresh_partner["name"],
        ])

        monitor.log("info", "wallet",
                    f"Admin topped up wallet for {partner['name']} (uuid={master_uuid}): "
                    f"+\u20ac{amount:.2f} \u2192 \u20ac{new_balance:.2f}. Reason: {reason[:200]}")
        _log.info("topup_wallet success: master_uuid=%s amount=%.2f new_balance=%.2f", master_uuid, amount, new_balance)
        return {
            "success":      True,
            "master_uuid":  master_uuid,
            "partner_name": partner["name"],
            "amount_added": amount,
            "old_balance":  old_balance,
            "new_balance":  new_balance,
            "reason":       reason,
            "message":      f"Added \u20ac{amount:.2f} to {partner['name']}'s wallet."
                            f" New balance: \u20ac{new_balance:.2f}.",
        }
    except Exception as exc:
        monitor.log("error", "wallet", f"Admin wallet top-up failed for uuid={master_uuid}: {str(exc)[:300]}")
        _log.error("topup_wallet error: master_uuid=%s error=%s", master_uuid, exc)
        return {"error": f"Wallet top-up failed: {exc}", "success": False}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8004"))
    print(f"Starting Kassa MCP server on port {port}...")
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)  # nosec B104
