# test_lease_model.py – Unit tests for the Authority Lease Model
# Tests all new handler functions added in the authority-lease feature.
# No live services required; all Odoo XML-RPC and RabbitMQ calls are mocked.

import xml.etree.ElementTree as ET
from unittest.mock import ANY, MagicMock, patch

import pytest

import receiver


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_idempotency_cache():
    receiver.seen_message_ids.clear()
    yield
    receiver.seen_message_ids.clear()


@pytest.fixture
def odoo():
    return 1, MagicMock()


# ── Helpers ────────────────────────────────────────────────────────────────────

_UUID = "550e8400-e29b-41d4-a716-446655440000"
_UUID2 = "550e8400-e29b-41d4-a716-446655440001"
_LEASE = "LEASE-001"


def _badge_root(scan_type: str, badge_id: str = "BADGE1") -> ET.Element:
    return ET.fromstring(
        "<message><header/>"
        f"<body><badge_id>{badge_id}</badge_id>"
        f"<scan_type>{scan_type}</scan_type>"
        "</body></message>"
    )


def _grant_root(identity_uuid: str, balance: str, lease_id: str) -> ET.Element:
    return ET.fromstring(
        "<message><header/>"
        f"<body><identity_uuid>{identity_uuid}</identity_uuid>"
        f"<current_balance>{balance}</current_balance>"
        f"<lease_id>{lease_id}</lease_id>"
        "</body></message>"
    )


def _topup_root(identity_uuid: str, add_amount: str, reason: str = "gift") -> ET.Element:
    return ET.fromstring(
        "<message><header/>"
        f"<body><identity_uuid>{identity_uuid}</identity_uuid>"
        f"<add_amount>{add_amount}</add_amount>"
        f"<reason>{reason}</reason>"
        "</body></message>"
    )


def _event_ended_root(session_id: str = "S1") -> ET.Element:
    return ET.fromstring(
        "<message><header/>"
        f"<body><session_id>{session_id}</session_id>"
        "<ended_at>2026-05-08T18:00:00Z</ended_at>"
        "</body></message>"
    )


def _badge_partner(lease_active: bool = False) -> dict:
    return {
        "id": 99, "name": "Alice", "x_user_id": _UUID,
        "x_wallet_balance": 25.0, "x_date_of_birth": False,
        "is_company": False, "x_lease_active": lease_active,
        "x_lease_id": _LEASE if lease_active else "",
        "x_lease_transaction_count": 3 if lease_active else 0,
    }


# ── process_badge_scan — check_in ─────────────────────────────────────────────

class TestBadgeScanCheckIn:

    @patch("receiver.send_typed_message")
    def test_sends_wallet_lease_request(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[_badge_partner()], True]
        receiver.process_badge_scan(_badge_root("check_in"), uid, models)
        mock_send.assert_called_once_with("wallet_lease_request", ANY)

    @patch("receiver.send_typed_message")
    def test_writes_lease_active_true_before_send(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[_badge_partner()], True]
        receiver.process_badge_scan(_badge_root("check_in"), uid, models)
        write_call = models.execute_kw.call_args_list[1]
        assert write_call[0][3] == "res.partner"
        assert write_call[0][4] == "write"
        vals = write_call[0][5][1]
        assert vals["x_lease_active"] is True
        assert vals["x_lease_transaction_count"] == 0

    @patch("receiver.send_typed_message")
    def test_skips_if_lease_already_active(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.return_value = [_badge_partner(lease_active=True)]
        receiver.process_badge_scan(_badge_root("check_in"), uid, models)
        mock_send.assert_not_called()
        assert models.execute_kw.call_count == 1  # only search_read

    @patch("receiver.send_typed_message")
    def test_skips_if_no_identity_uuid(self, mock_send, odoo):
        uid, models = odoo
        partner = _badge_partner()
        partner["x_user_id"] = ""
        models.execute_kw.return_value = [partner]
        receiver.process_badge_scan(_badge_root("check_in"), uid, models)
        mock_send.assert_not_called()

    @patch("receiver.send_error_to_queue")
    @patch("receiver.send_typed_message")
    def test_sends_error_when_badge_not_found(self, mock_send, mock_error, odoo):
        uid, models = odoo
        models.execute_kw.return_value = []
        receiver.process_badge_scan(_badge_root("check_in"), uid, models)
        mock_send.assert_not_called()
        mock_error.assert_called_once()


# ── process_badge_scan — check_out ────────────────────────────────────────────

class TestBadgeScanCheckOut:

    @patch("receiver.send_typed_message")
    def test_sends_wallet_lease_return(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[_badge_partner(lease_active=True)], True]
        receiver.process_badge_scan(_badge_root("check_out"), uid, models)
        mock_send.assert_called_once_with("wallet_lease_return", ANY)

    @patch("receiver.send_typed_message")
    def test_clears_lease_fields_after_return(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[_badge_partner(lease_active=True)], True]
        receiver.process_badge_scan(_badge_root("check_out"), uid, models)
        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        assert vals["x_lease_active"] is False
        assert vals["x_lease_id"] == ""
        assert vals["x_lease_transaction_count"] == 0

    @patch("receiver.send_typed_message")
    def test_lease_return_includes_correct_balance_and_tx_count(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[_badge_partner(lease_active=True)], True]
        with patch("receiver.build_wallet_lease_return_xml") as mock_builder:
            mock_builder.return_value = "<xml/>"
            receiver.process_badge_scan(_badge_root("check_out"), uid, models)
        mock_builder.assert_called_once_with(
            identity_uuid=_UUID,
            final_balance=25.0,
            lease_id=_LEASE,
            transaction_count=3,
        )

    @patch("receiver.send_typed_message")
    def test_skips_if_no_active_lease(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.return_value = [_badge_partner(lease_active=False)]
        receiver.process_badge_scan(_badge_root("check_out"), uid, models)
        mock_send.assert_not_called()
        assert models.execute_kw.call_count == 1  # only search_read

    @patch("receiver.send_typed_message")
    def test_skips_if_no_identity_uuid(self, mock_send, odoo):
        uid, models = odoo
        partner = _badge_partner(lease_active=True)
        partner["x_user_id"] = ""
        models.execute_kw.return_value = [partner]
        receiver.process_badge_scan(_badge_root("check_out"), uid, models)
        mock_send.assert_not_called()
        assert models.execute_kw.call_count == 1  # guard fires before any write


# ── process_wallet_lease_grant ────────────────────────────────────────────────

class TestWalletLeaseGrant:

    @patch("receiver.send_typed_message")
    def test_writes_balance_lease_id_and_sets_active(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[{"id": 5}], True]
        receiver.process_wallet_lease_grant(_grant_root(_UUID, "42.50", _LEASE), uid, models)
        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        assert vals["x_wallet_balance"] == 42.50
        assert vals["x_lease_id"] == _LEASE
        assert vals["x_lease_active"] is True

    @patch("receiver.send_typed_message")
    def test_noop_when_partner_not_found(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.return_value = []
        receiver.process_wallet_lease_grant(_grant_root(_UUID, "10.00", _LEASE), uid, models)
        assert models.execute_kw.call_count == 1
        mock_send.assert_not_called()

    def test_raises_on_missing_identity_uuid(self, odoo):
        uid, models = odoo
        root = ET.fromstring(
            "<message><header/><body>"
            "<identity_uuid></identity_uuid>"
            "<current_balance>10.00</current_balance>"
            "<lease_id>X</lease_id>"
            "</body></message>"
        )
        with pytest.raises(ValueError, match="identity_uuid missing"):
            receiver.process_wallet_lease_grant(root, uid, models)

    def test_raises_on_invalid_balance(self, odoo):
        uid, models = odoo
        with pytest.raises(ValueError, match="invalid current_balance"):
            receiver.process_wallet_lease_grant(_grant_root(_UUID, "not-a-number", _LEASE), uid, models)


# ── process_wallet_remote_topup ───────────────────────────────────────────────

class TestWalletRemoteTopup:

    def _partner(self, lease_active: bool = True) -> dict:
        return {"id": 7, "x_wallet_balance": 20.0, "x_lease_active": lease_active}

    @patch("receiver.send_typed_message")
    def test_calls_atomic_add_wallet_amount(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[self._partner()], 25.0]
        receiver.process_wallet_remote_topup(_topup_root(_UUID, "5.0"), uid, models)
        second_call = models.execute_kw.call_args_list[1]
        assert second_call[0][3] == "pos.order"
        assert second_call[0][4] == "action_add_wallet_amount"
        assert second_call[0][5] == [7, 5.0]

    @patch("receiver.send_typed_message")
    def test_sends_balance_update_with_authority_kassa(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[self._partner()], 25.0]
        with patch("receiver.build_wallet_balance_update_xml") as mock_builder:
            mock_builder.return_value = "<xml/>"
            receiver.process_wallet_remote_topup(_topup_root(_UUID, "5.0"), uid, models)
        mock_builder.assert_called_once_with(
            identity_uuid=_UUID,
            new_balance=25.0,
            authority="kassa",
            status="active",
        )
        mock_send.assert_called_once_with("wallet_balance_update", "<xml/>")

    @patch("receiver.send_typed_message")
    def test_rejects_topup_when_no_active_lease(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.return_value = [self._partner(lease_active=False)]
        receiver.process_wallet_remote_topup(_topup_root(_UUID, "5.0"), uid, models)
        assert models.execute_kw.call_count == 1  # only search_read, no action_add_wallet_amount
        mock_send.assert_not_called()

    def test_raises_on_missing_identity_uuid(self, odoo):
        uid, models = odoo
        root = ET.fromstring(
            "<message><header/><body>"
            "<identity_uuid></identity_uuid>"
            "<add_amount>5.0</add_amount><reason>gift</reason>"
            "</body></message>"
        )
        with pytest.raises(ValueError, match="identity_uuid missing"):
            receiver.process_wallet_remote_topup(root, uid, models)

    def test_raises_on_invalid_amount(self, odoo):
        uid, models = odoo
        with pytest.raises(ValueError, match="invalid add_amount"):
            receiver.process_wallet_remote_topup(_topup_root(_UUID, "not-a-number"), uid, models)

    @patch("receiver.send_typed_message")
    def test_noop_when_partner_not_found(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.return_value = []
        receiver.process_wallet_remote_topup(_topup_root(_UUID, "5.0"), uid, models)
        assert models.execute_kw.call_count == 1
        mock_send.assert_not_called()


# ── process_event_ended ────────────────────────────────────────────────────────

class TestEventEnded:

    def _partner(self, pid: int, uuid: str, balance: float, lease_id: str, tx: int) -> dict:
        return {
            "id": pid, "x_user_id": uuid, "x_wallet_balance": balance,
            "x_lease_id": lease_id, "x_lease_transaction_count": tx,
        }

    @patch("receiver.send_typed_message")
    def test_sends_lease_return_for_each_active_partner(self, mock_send, odoo):
        uid, models = odoo
        partners = [
            self._partner(1, _UUID, 10.0, "L1", 2),
            self._partner(2, _UUID2, 5.0, "L2", 1),
        ]
        models.execute_kw.side_effect = [partners, True]
        receiver.process_event_ended(_event_ended_root(), uid, models)
        assert mock_send.call_count == 2
        assert all(c[0][0] == "wallet_lease_return" for c in mock_send.call_args_list)

    @patch("receiver.send_typed_message")
    def test_single_bulk_write_clears_all_leases(self, mock_send, odoo):
        uid, models = odoo
        partners = [
            self._partner(1, _UUID, 10.0, "L1", 2),
            self._partner(2, _UUID2, 5.0, "L2", 1),
        ]
        models.execute_kw.side_effect = [partners, True]
        receiver.process_event_ended(_event_ended_root(), uid, models)
        # Exactly 2 execute_kw calls: search_read + bulk write
        assert models.execute_kw.call_count == 2
        write_call = models.execute_kw.call_args_list[1]
        assert write_call[0][3] == "res.partner"
        assert write_call[0][4] == "write"
        cleared_ids = write_call[0][5][0]
        assert set(cleared_ids) == {1, 2}
        vals = write_call[0][5][1]
        assert vals == {"x_lease_active": False, "x_lease_id": "", "x_lease_transaction_count": 0}

    @patch("receiver.send_typed_message")
    def test_no_write_when_no_active_leases(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.return_value = []
        receiver.process_event_ended(_event_ended_root(), uid, models)
        assert models.execute_kw.call_count == 1  # only search_read
        mock_send.assert_not_called()

    @patch("receiver.send_typed_message")
    def test_skips_partner_without_identity_uuid(self, mock_send, odoo):
        uid, models = odoo
        partners = [
            self._partner(1, "", 10.0, "L1", 2),       # no identity_uuid — must be skipped
            self._partner(2, _UUID2, 5.0, "L2", 1),    # valid — must be processed
        ]
        models.execute_kw.side_effect = [partners, True]
        receiver.process_event_ended(_event_ended_root(), uid, models)
        assert mock_send.call_count == 1  # only the valid partner
        write_call = models.execute_kw.call_args_list[1]
        cleared_ids = write_call[0][5][0]
        assert 1 not in cleared_ids
        assert 2 in cleared_ids

    @patch("receiver.send_typed_message")
    def test_partial_failure_clears_only_successful_partners(self, mock_send, odoo):
        uid, models = odoo
        partners = [
            self._partner(1, _UUID, 10.0, "L1", 2),   # will fail
            self._partner(2, _UUID2, 5.0, "L2", 1),   # will succeed
        ]
        models.execute_kw.side_effect = [partners, True]

        call_count = {"n": 0}

        def raise_on_first(msg_type, xml):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("RabbitMQ unavailable")

        mock_send.side_effect = raise_on_first
        receiver.process_event_ended(_event_ended_root(), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        cleared_ids = write_call[0][5][0]
        assert 1 not in cleared_ids   # first partner failed — not cleared
        assert 2 in cleared_ids        # second partner succeeded — cleared
