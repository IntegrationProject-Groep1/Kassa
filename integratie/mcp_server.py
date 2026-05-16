"""
Kassa MCP Server — exposes Odoo 17 POS data as MCP tools.

Standalone process. Run with:
    python kassa_mcp_server.py

Requires env vars: ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASS
Optional: PORT (default 8004)
"""
import os
import xmlrpc.client  # nosec B411
from typing import Any, cast

import defusedxml.xmlrpc
from dotenv import load_dotenv
from fastmcp import FastMCP

defusedxml.xmlrpc.monkey_patch()
load_dotenv()

mcp = FastMCP("kassa")

_URL = os.getenv("ODOO_URL", "")
_DB = os.getenv("ODOO_DB", "")
_USER = os.getenv("ODOO_USER", "")
_PASSWORD = os.getenv("ODOO_PASS", "")

_uid: int | None = None


def _get_uid() -> int:
    global _uid
    if _uid is None:
        common = xmlrpc.client.ServerProxy(f"{_URL}/xmlrpc/2/common")
        _uid = cast(int, common.authenticate(_DB, _USER, _PASSWORD, {}))
        if not _uid:
            raise RuntimeError("Odoo authentication failed — check ODOO_USER / ODOO_PASS")
    return _uid


def _odoo(model: str, method: str, args: list, kwargs: dict | None = None) -> Any:
    global _uid
    models = xmlrpc.client.ServerProxy(f"{_URL}/xmlrpc/2/object")
    try:
        return models.execute_kw(_DB, _get_uid(), _PASSWORD, model, method, args, kwargs or {})
    except xmlrpc.client.Fault as exc:
        if "Access Denied" in str(exc):
            _uid = None
        raise


@mcp.tool()
def get_sales_summary(date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
    """
    Get a POS sales revenue summary.
    date_from / date_to: optional ISO date strings, e.g. '2026-05-01'.
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
def get_recent_orders(limit: int = 20) -> dict[str, Any]:
    """
    Get the most recent POS orders (default 20, max 100).
    Includes the customer's current wallet balance and master UUID.

    POS orders only (live on-site sales). Wallet balance in the response is the
    LIVE Odoo value, not the CRM cache.
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
def get_wallet_by_master_uuid(master_uuid: str) -> dict[str, Any]:
    """
    Get the LIVE wallet balance for a member by their Master UUID (from CRM).

    Call this whenever `crm__get_member_wallet` returns Wallet_Status__c='Leased'
    — during a lease Kassa holds the source-of-truth balance, not CRM.
    Returns the Odoo partner record with x_wallet_balance, x_user_id, x_badge_id,
    x_outstanding_amount, x_pending_topup_balance, x_payment_status.
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
            "wallet_balance": p.get("x_wallet_balance", 0),
            "pending_topup": p.get("x_pending_topup_balance", 0),
            "outstanding_amount": p.get("x_outstanding_amount", 0),
            "payment_status": p.get("x_payment_status") or None,
            "currency": "EUR",
            "source": "kassa_live",
        }
    except Exception as exc:
        return {"error": f"Odoo unavailable: {exc}", "found": False}


@mcp.tool()
def get_orders_by_email(email: str, limit: int = 50) -> dict[str, Any]:
    """
    Get POS orders for a member identified by their email address.
    Looks up the Odoo partner by email then returns their order history.
    Use this when the admin asks what a specific person bought at the event.
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
                {"order_id": o["name"], "total": o["amount_total"], "date": o["date_order"], "status": o["state"]}
                for o in orders
            ],
            "count": len(orders),
            "currency": "EUR",
        }
    except Exception as exc:
        return {"error": f"Odoo unavailable: {exc}", "orders": [], "count": 0}


@mcp.tool()
def process_refund(order_id: str, reason: str) -> dict[str, Any]:
    """
    Issue a refund for a POS order.
    order_id: the order name/reference (e.g. 'POS/2026/0042').
    reason: written reason for the refund (required).

    WRITE operation. Always confirm with the admin before calling
    (per chatbot system prompt Rule 4).
    """
    if not reason or not reason.strip():
        return {"error": "A reason is required to process a refund.", "success": False}
    try:
        ids = _odoo("pos.order", "search", [[["name", "=", order_id]]])
        if not ids:
            return {"error": f"Order '{order_id}' not found.", "success": False}
        result = _odoo("pos.order", "refund", [ids])
        return {
            "success": True,
            "order_id": order_id,
            "reason": reason,
            "refund_result": result,
            "message": f"Refund initiated for order {order_id}.",
        }
    except Exception as exc:
        return {"error": f"Refund failed: {exc}", "success": False}


@mcp.tool()
def discover_odoo_schema() -> dict[str, Any]:
    """
    Discover the actual field names available on Odoo pos.order and res.partner.
    Use this to debug why Kassa queries return no results — confirms whether custom
    wallet fields (x_wallet_balance, x_user_id, x_badge_id) exist in this Odoo instance.
    """
    try:
        order_fields = _odoo("pos.order", "fields_get", [], {"attributes": ["string", "type"]})
        partner_fields = _odoo("res.partner", "fields_get", [], {"attributes": ["string", "type"]})

        # Extract just x_ custom fields and wallet-related fields for clarity
        keep_order = ("name", "state", "amount_total", "date_order", "partner_id")
        order_summary = {k: v for k, v in order_fields.items() if k.startswith("x_") or k in keep_order}
        keep_partner = ("name", "email", "id")
        partner_summary = {k: v for k, v in partner_fields.items() if k.startswith("x_") or k in keep_partner}

        # Check a live order count
        order_count = _odoo("pos.order", "search_count", [[]])
        paid_count = _odoo("pos.order", "search_count", [[["state", "in", ["paid", "done", "invoiced"]]]])

        wallet_fields = [
            k for k in partner_fields
            if "wallet" in k.lower() or "x_user" in k.lower() or "badge" in k.lower()
        ]
        return {
            "pos_order_custom_fields": order_summary,
            "res_partner_custom_fields": partner_summary,
            "total_pos_orders": order_count,
            "paid_done_invoiced_orders": paid_count,
            "wallet_fields_found": wallet_fields,
        }
    except Exception as exc:
        return {"error": f"Odoo schema discovery failed: {exc}"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8004"))
    print(f"Starting Kassa MCP server on port {port}...")
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)  # nosec B104
