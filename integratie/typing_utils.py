"""
typing_utils.py — Type definitions and protocols for the Kassa integration service.
"""

from typing import Any, Protocol, TypedDict, Union, List, Dict


# Odoo XML-RPC search_read result item
class OdooRecord(TypedDict, total=False):
    id: int
    name: str
    email: str
    x_user_id: str
    x_badge_id: str
    x_wallet_balance: float
    x_date_of_birth: Union[str, bool]
    is_company: bool
    parent_id: Union[List[Union[int, str]], bool]
    active: bool
    state: str
    lines: List[int]
    amount_total: float
    amount_tax: float
    payment_ids: List[int]
    create_date: str
    session_id: Union[List[Union[int, str]], bool]
    x_rabbitmq_sent: bool
    x_wallet_updated: bool
    x_payment_message_id: str
    vat: Union[str, bool]


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
    ) -> Any: ...


class OdooCommonProxy(Protocol):
    def authenticate(
        self,
        db: str,
        user: str,
        password: str,
        user_agent_env: Dict[str, Any],
    ) -> int: ...
