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
        return {
            "total_revenue": round(total_revenue, 2),
            "order_count": len(orders),
            "currency": "EUR",
            "period": {"from": date_from, "to": date_to},
            "by_day": [{"date": d, "revenue": r} for d, r in sorted(by_day.items())],
        }
    except Exception as exc:
        return {"error": f"Odoo unavailable: {exc}", "total_revenue": 0, "order_count": 0}


@mcp.tool()
def get_recent_orders(limit: int = 20) -> dict[str, Any]:
    """
    Get the most recent POS orders (default 20, max 100).
    Includes the customer's current wallet balance and master UUID.
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
        return {"wallets": wallets, "count": len(wallets), "total_balance": round(total_balance, 2), "currency": "EUR"}
    except Exception as exc:
        return {"error": f"Odoo unavailable: {exc}", "wallets": [], "count": 0}


@mcp.tool()
def process_refund(order_id: str, reason: str) -> dict[str, Any]:
    """
    Issue a refund for a POS order.
    order_id: the order name/reference (e.g. 'POS/2026/0042').
    reason: written reason for the refund (required).

    NOTE: This is a WRITE operation. Always confirm with the admin before calling this.
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


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8004"))
    print(f"Starting Kassa MCP server on port {port}...")
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)  # nosec B104
