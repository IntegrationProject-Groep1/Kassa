# test_wallet_balance_guard.py
#
# Tests for two related correctness properties of the wallet-balance feature:
#
# 1. LEASE-TIMING CONTRACT
#    The POS may only show a visitor's wallet balance once the CRM has confirmed
#    the lease (x_lease_active=True AND x_lease_id non-empty).  Between the QR/
#    badge scan (which sends wallet_lease_request and optimistically sets
#    x_lease_active=True with x_lease_id="") and the arrival of wallet_lease_grant
#    (which sets the real x_lease_id and x_wallet_balance), the POS must show
#    nothing — to avoid displaying a misleading €0.00 badge.
#
# 2. INSUFFICIENT-BALANCE GUARD
#    action_process_wallet_payment now raises ValueError when the balance is below
#    the order amount.  order_poller must catch that exception, log it, set
#    ok_wallet=False, and still emit consumption_order and payment_registered so
#    the order is not silently dropped.

import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import pytest

import receiver
from order_poller import OrderPoller


_UUID = "550e8400-e29b-41d4-a716-446655440000"
_LEASE = "LEASE-99"


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_idempotency_cache():
    receiver.seen_message_ids.clear()
    yield
    receiver.seen_message_ids.clear()


@pytest.fixture
def odoo():
    return 1, MagicMock()


@pytest.fixture
def poller():
    p = OrderPoller()
    p.odoo_db = "test_db"
    p.odoo_uid = 1
    p.odoo_pass = "admin"
    p.models = MagicMock()
    p.processed_orders = {}
    return p


# ── Helpers ────────────────────────────────────────────────────────────────────

def _qr_root(identity_uuid: str = _UUID, location: str = "entrance") -> ET.Element:
    return ET.fromstring(
        "<message><header/>"
        f"<body><identity_uuid>{identity_uuid}</identity_uuid>"
        f"<location>{location}</location>"
        "<scanned_at>2026-05-08T12:00:00Z</scanned_at>"
        "</body></message>"
    )


def _grant_root(balance: str = "42.50", lease_id: str = _LEASE) -> ET.Element:
    return ET.fromstring(
        "<message><header/>"
        f"<body><identity_uuid>{_UUID}</identity_uuid>"
        f"<current_balance>{balance}</current_balance>"
        f"<lease_id>{lease_id}</lease_id>"
        "</body></message>"
    )


def _partner(lease_active: bool = False, lease_id: str = "") -> dict:
    return {
        "id": 10, "name": "Jan", "x_user_id": _UUID,
        "x_wallet_balance": 25.0, "x_date_of_birth": False,
        "is_company": False,
        "x_lease_active": lease_active,
        "x_lease_id": lease_id,
        "x_lease_transaction_count": 0,
    }


def _customer(balance: float = 3.0) -> dict:
    return {
        "id": 55, "x_wallet_balance": balance, "x_user_id": "USR-55",
        "is_company": False, "parent_id": False, "email": "",
    }


def _order(amount: float = 4.0) -> dict:
    return {
        "id": 77, "lines": [], "amount_total": amount,
        "payment_ids": [8], "x_wallet_updated": False,
        "create_date": "2026-05-08 12:00:00",
    }


def _mock_sender_xmls(mock_sender):
    mock_sender.build_consumption_order_xml.return_value = (
        "<message><header><message_id>c-1</message_id></header></message>"
    )
    mock_sender.build_payment_registered_xml.return_value = (
        "<message><header><message_id>p-1</message_id></header></message>"
    )
    mock_sender.build_wallet_balance_update_xml.return_value = (
        "<message><header><message_id>w-1</message_id></header></message>"
    )
    mock_sender.send_typed_message.return_value = True


# ── Lease-timing contract ─────────────────────────────────────────────────────

class TestLeaseTimingContract:
    """
    Verifies the two-step state machine that the POS templates rely on:

      QR scan  →  x_lease_active=True, x_lease_id=""   (PENDING  — hide balance)
      Grant    →  x_lease_active=True, x_lease_id=<id>  (CONFIRMED — show balance)

    The POS condition is:  partner.x_lease_active && partner.x_lease_id
    Both fields must be loaded via pos_session._loader_params_res_partner and
    KASSA_PARTNER_FIELDS so they are available in the OWL template.
    """

    @patch("receiver.send_typed_message")
    def test_qr_scan_writes_empty_lease_id(self, mock_send, odoo):
        """
        After QR scan, lease is REQUESTED: x_lease_id must be "" so the POS
        template condition (x_lease_active && x_lease_id) is falsy and the
        wallet balance notification stays hidden.
        """
        uid, models = odoo
        models.execute_kw.side_effect = [[_partner()], True]

        receiver.process_badge_scan(_qr_root(), uid, models)

        write_vals = models.execute_kw.call_args_list[1][0][5][1]
        assert write_vals["x_lease_active"] is True
        assert write_vals["x_lease_id"] == "", (
            "x_lease_id must be empty after scan so POS does not show balance "
            "before the CRM confirms the grant"
        )

    @patch("receiver.send_typed_message")
    def test_lease_grant_writes_non_empty_lease_id_and_balance(self, mock_send, odoo):
        """
        After wallet_lease_grant, lease is CONFIRMED: x_lease_id is non-empty
        and x_wallet_balance carries the authoritative CRM value.  The POS
        template condition becomes truthy and the notification appears.
        """
        uid, models = odoo
        models.execute_kw.side_effect = [[{"id": 10}], True]

        receiver.process_wallet_lease_grant(_grant_root("42.50", _LEASE), uid, models)

        write_vals = models.execute_kw.call_args_list[1][0][5][1]
        assert write_vals["x_lease_id"] == _LEASE, (
            "x_lease_id must be set after grant so POS shows the balance"
        )
        assert write_vals["x_lease_active"] is True
        assert write_vals["x_wallet_balance"] == 42.50

    @patch("receiver.send_typed_message")
    def test_full_qr_to_grant_sequence_transitions_through_pending(self, mock_send, odoo):
        """
        End-to-end: QR scan → pending (x_lease_id="") → grant → confirmed (x_lease_id set).
        The window between these two states is where the POS must stay silent.
        """
        uid, models = odoo

        # Step 1: visitor scans QR — lease REQUESTED
        models.execute_kw.side_effect = [[_partner()], True]
        receiver.process_badge_scan(_qr_root(), uid, models)
        pending_vals = models.execute_kw.call_args_list[1][0][5][1]
        assert pending_vals["x_lease_id"] == ""  # POS hides balance in this state

        # Step 2: CRM delivers grant — lease CONFIRMED
        models.execute_kw.reset_mock()
        models.execute_kw.side_effect = [[{"id": 10}], True]
        receiver.process_wallet_lease_grant(_grant_root("42.50", _LEASE), uid, models)
        confirmed_vals = models.execute_kw.call_args_list[1][0][5][1]
        assert confirmed_vals["x_lease_id"] == _LEASE  # POS now shows balance
        assert confirmed_vals["x_wallet_balance"] == 42.50

    @patch("receiver.send_typed_message")
    def test_lease_return_clears_both_lease_fields(self, mock_send, odoo):
        """
        After lease return, x_lease_active=False and x_lease_id="" so the POS
        hides the wallet notification immediately on the next bus update.
        """
        uid, models = odoo
        partner_with_lease = {
            "id": 10, "x_user_id": _UUID, "x_wallet_balance": 15.0,
            "x_lease_id": _LEASE, "x_lease_transaction_count": 3,
        }
        models.execute_kw.side_effect = [[partner_with_lease], True]

        receiver._return_lease(10, uid, models)

        write_vals = models.execute_kw.call_args_list[1][0][5][1]
        assert write_vals["x_lease_active"] is False
        assert write_vals["x_lease_id"] == ""

    @patch("receiver.send_typed_message")
    def test_second_qr_scan_skips_when_lease_already_confirmed(self, mock_send, odoo):
        """
        If a visitor scans again while the lease is already confirmed (e.g. they
        passed a second scanner), no new lease request is sent and the balance
        stays at its current confirmed value.
        """
        uid, models = odoo
        confirmed_partner = _partner(lease_active=True, lease_id=_LEASE)
        models.execute_kw.return_value = [confirmed_partner]

        receiver.process_badge_scan(_qr_root(), uid, models)

        mock_send.assert_not_called()
        assert models.execute_kw.call_count == 1  # only the search_read, no write

    @patch("receiver.send_typed_message")
    def test_pending_topup_is_merged_into_confirmed_balance(self, mock_send, odoo):
        """
        A remote top-up that arrives while the lease is still pending
        (x_lease_active=True, x_lease_id="") is parked in x_pending_topup_balance.
        When the grant arrives, it is merged into the authoritative balance.
        """
        uid, models = odoo
        # Partner has a pending top-up that arrived before the grant
        partner_with_pending = {"id": 10, "x_pending_topup_balance": 5.0}
        models.execute_kw.side_effect = [[partner_with_pending], True]

        receiver.process_wallet_lease_grant(_grant_root("10.00", _LEASE), uid, models)

        write_vals = models.execute_kw.call_args_list[1][0][5][1]
        assert write_vals["x_wallet_balance"] == 15.0, (
            "CRM balance (10.00) + pending top-up (5.00) must be merged to 15.00"
        )
        assert write_vals["x_pending_topup_balance"] == 0.0


# ── Insufficient-balance guard in order_poller ────────────────────────────────

class TestWalletInsufficientBalance:
    """
    Since action_process_wallet_payment now raises ValueError when balance < amount,
    order_poller must handle the exception gracefully:
      - ok_wallet = False  →  overall return is False
      - no wallet_balance_update message emitted
      - no lease tx count increment
      - consumption_order and payment_registered_consumption still sent
    """

    @patch("order_poller.sender")
    def test_insufficient_balance_makes_ok_false(self, mock_sender, poller):
        """Overall result is False when the wallet deduction fails."""
        poller.models.execute_kw.side_effect = [
            [{"payment_method_id": (3, "Badge Wallet"), "amount": 4.0}],
            ValueError("Insufficient wallet balance for partner 55: balance=€3.00, required=€4.00"),
        ]
        _mock_sender_xmls(mock_sender)

        ok, _corr, _pay = poller._process_consumption(
            _order(4.0), _customer(balance=3.0), is_anonymous=False
        )

        assert ok is False

    @patch("order_poller.sender")
    def test_insufficient_balance_no_wallet_balance_update(self, mock_sender, poller):
        """wallet_balance_update must NOT be published when the deduction raises."""
        poller.models.execute_kw.side_effect = [
            [{"payment_method_id": (3, "Badge Wallet"), "amount": 4.0}],
            ValueError("Insufficient wallet balance"),
        ]
        _mock_sender_xmls(mock_sender)

        poller._process_consumption(_order(4.0), _customer(balance=3.0), is_anonymous=False)

        sent = [c[0][0] for c in mock_sender.send_typed_message.call_args_list]
        assert "wallet_balance_update" not in sent

    @patch("order_poller.sender")
    def test_insufficient_balance_still_sends_consumption_and_payment(self, mock_sender, poller):
        """
        consumption_order and payment_registered_consumption are emitted even
        when the wallet deduction fails so the order is not silently abandoned.
        """
        poller.models.execute_kw.side_effect = [
            [{"payment_method_id": (3, "Badge Wallet"), "amount": 4.0}],
            ValueError("Insufficient wallet balance"),
        ]
        _mock_sender_xmls(mock_sender)

        poller._process_consumption(_order(4.0), _customer(balance=3.0), is_anonymous=False)

        sent = [c[0][0] for c in mock_sender.send_typed_message.call_args_list]
        assert "consumption_order" in sent
        assert "payment_registered_consumption" in sent

    @patch("order_poller.sender")
    def test_insufficient_balance_no_lease_tx_count_increment(self, mock_sender, poller):
        """Lease transaction count must not be incremented when deduction failed."""
        poller.models.execute_kw.side_effect = [
            [{"payment_method_id": (3, "Badge Wallet"), "amount": 4.0}],
            ValueError("Insufficient wallet balance"),
        ]
        _mock_sender_xmls(mock_sender)

        poller._process_consumption(_order(4.0), _customer(balance=3.0), is_anonymous=False)

        tx_calls = [
            c for c in poller.models.execute_kw.call_args_list
            if len(c[0]) > 4 and c[0][4] == "action_increment_lease_tx_count"
        ]
        assert len(tx_calls) == 0

    @patch("order_poller.sender")
    def test_sufficient_balance_succeeds_and_emits_wallet_update(self, mock_sender, poller):
        """Control: when balance covers the order, everything succeeds normally."""
        poller.models.execute_kw.side_effect = [
            [{"payment_method_id": (3, "Badge Wallet"), "amount": 2.50}],
            0.50,  # new balance after deduction: 3.00 - 2.50
        ]
        _mock_sender_xmls(mock_sender)

        ok, _corr, _pay = poller._process_consumption(
            _order(2.50), _customer(balance=3.0), is_anonymous=False
        )

        assert ok is True
        sent = [c[0][0] for c in mock_sender.send_typed_message.call_args_list]
        assert "wallet_balance_update" in sent
        mock_sender.build_wallet_balance_update_xml.assert_called_once_with(
            identity_uuid="USR-55",
            new_balance=0.50,
            authority=None,   # x_lease_active not set in customer_info fixture
            status=None,
        )

    @patch("order_poller.sender")
    def test_already_updated_wallet_is_idempotent(self, mock_sender, poller):
        """x_wallet_updated=True on the order means the deduction was already done;
        no second action_process_wallet_payment call is made."""
        order = _order(4.0)
        order["x_wallet_updated"] = True

        poller.models.execute_kw.side_effect = [
            [{"payment_method_id": (3, "Badge Wallet"), "amount": 4.0}],
        ]
        _mock_sender_xmls(mock_sender)

        poller._process_consumption(order, _customer(balance=10.0), is_anonymous=False)

        wallet_calls = [
            c for c in poller.models.execute_kw.call_args_list
            if len(c[0]) > 4 and c[0][4] == "action_process_wallet_payment"
        ]
        assert len(wallet_calls) == 0
