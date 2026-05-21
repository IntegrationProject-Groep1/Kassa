"""
typing_utils.py — Type definitions and protocols for the Kassa integration service.

Odoo's XML-RPC API (xmlrpc.client.ServerProxy) returns plain Python dicts with no
type information. This module adds TypedDict definitions so IDEs and mypy can catch
field-name typos and type mismatches at development time — it has no effect at runtime.

Key convention: fields prefixed with `x_` are Odoo custom fields created by
odoo_setup.py during the service startup. They do not exist in a vanilla Odoo install.

Odoo XML-RPC encodes absent/unset fields as Python `False` (not `None`). This is why
several fields below are typed as `Union[str, bool]` or `Union[list, bool]` — the `bool`
half covers the case where the field is absent (Odoo returns `False`).
"""

from typing import Any, Protocol, TypedDict, Union, List, Dict


# Odoo XML-RPC search_read result item
class OdooRecord(TypedDict, total=False):
    id: int
    name: str                              # Full display name (first + last in Odoo)
    email: str
    x_user_id: str                         # Master UUID from Identity Service (written by receiver/poller)
    x_badge_id: str                        # Physical badge or QR identifier (written by receiver on badge_assigned)
    x_wallet_balance: float                # Current leased wallet balance; authoritative while x_lease_active=True
    x_date_of_birth: Union[str, bool]      # ISO date string or False when absent
    is_company: bool                       # True for company-type customers (VAT required per §11.1)
    parent_id: Union[List[Union[int, str]], bool]  # [id, name] pair or False for top-level partners
    active: bool
    state: str                             # pos.order state: draft, paid, done, invoiced, cancel
    lines: List[int]                       # pos.order line IDs (used for order-line iteration)
    amount_total: float
    amount_tax: float
    payment_ids: List[int]                 # pos.payment record IDs (determines payment method used)
    create_date: str
    session_id: Union[List[Union[int, str]], bool]  # [id, name] pair for the POS session, or False
    x_rabbitmq_sent: bool                  # Flag: order already published to RabbitMQ (prevents re-publish)
    x_wallet_updated: bool                 # Flag: wallet_balance_update already sent for this order
    x_payment_message_id: str             # UUID of the payment_registered message (idempotency key for CRM)
    vat: Union[str, bool]                  # VAT number string or False; required for company partners


# Protocol for the Odoo models proxy (ServerProxy)
class OdooModelsProxy(Protocol):
    def execute_kw(
        self,
        db: str,
        uid: int,
        password: str,
        model: str,
        method: str,
        args: List[Any],
        kwargs: Dict[str, Any] = ...,
    ) -> Any:
        ...


class OdooCommonProxy(Protocol):
    def authenticate(
        self,
        db: str,
        user: str,
        password: str,
        user_agent_env: Dict[str, Any],
    ) -> int:
        ...
