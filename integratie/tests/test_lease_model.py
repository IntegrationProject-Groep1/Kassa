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


def _badge_root(location: str = "entrance", badge_id: str = "BADGE1") -> ET.Element:
    return ET.fromstring(
        "<message><header/>"
        f"<body><badge_id>{badge_id}</badge_id>"
        f"<location>{location}</location>"
        "<scanned_at>2026-05-08T12:00:00Z</scanned_at>"
        "</body></message>"
    )


def _qr_root(location: str = "entrance", identity_uuid: str = _UUID) -> ET.Element:
    return ET.fromstring(
        "<message><header/>"
        f"<body><identity_uuid>{identity_uuid}</identity_uuid>"
        f"<location>{location}</location>"
        "<scanned_at>2026-05-08T12:00:00Z</scanned_at>"
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


# ── process_badge_scan — entrance (check_in) ──────────────────────────────────

class TestBadgeScanCheckIn:

    @patch("receiver.send_typed_message")
    def test_sends_wallet_lease_request_on_entrance(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[_badge_partner()], True]
        receiver.process_badge_scan(_badge_root("entrance"), uid, models)
        mock_send.assert_called_once_with("wallet_lease_request", ANY)

    @patch("receiver.send_typed_message")
    def test_writes_lease_active_true_after_send(self, mock_send, odoo):
        """Send fires first; Odoo write follows so a send failure leaves state clean."""
        uid, models = odoo
        call_order = []

        def track(msg_type, xml):
            call_order.append("send")

        def track_kw(*args):
            if args[4] == "search_read":
                return [_badge_partner()]
            call_order.append("write")
            return True

        mock_send.side_effect = track
        models.execute_kw.side_effect = track_kw
        receiver.process_badge_scan(_badge_root("entrance"), uid, models)

        assert call_order == ["send", "write"]
        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        assert vals["x_lease_active"] is True
        assert vals["x_lease_id"] == ""
        assert vals["x_lease_transaction_count"] == 0

    @patch("receiver.send_typed_message")
    def test_skips_if_lease_already_active(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.return_value = [_badge_partner(lease_active=True)]
        receiver.process_badge_scan(_badge_root("entrance"), uid, models)
        mock_send.assert_not_called()
        assert models.execute_kw.call_count == 1  # only search_read

    @patch("receiver.send_typed_message")
    def test_skips_if_no_identity_uuid(self, mock_send, odoo):
        uid, models = odoo
        partner = _badge_partner()
        partner["x_user_id"] = ""
        models.execute_kw.return_value = [partner]
        receiver.process_badge_scan(_badge_root("entrance"), uid, models)
        mock_send.assert_not_called()

    @patch("receiver.send_typed_message")
    def test_bar_scan_triggers_lease(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[_badge_partner()], True]
        receiver.process_badge_scan(_badge_root("bar"), uid, models)
        mock_send.assert_called_once_with("wallet_lease_request", ANY)

    @patch("receiver.send_typed_message")
    def test_session_scan_does_not_trigger_lease(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.return_value = [_badge_partner()]
        receiver.process_badge_scan(_badge_root("session"), uid, models)
        mock_send.assert_not_called()

    @patch("receiver.send_error_to_queue")
    @patch("receiver.send_typed_message")
    def test_sends_error_when_badge_not_found(self, mock_send, mock_error, odoo):
        uid, models = odoo
        models.execute_kw.return_value = []
        receiver.process_badge_scan(_badge_root("entrance"), uid, models)
        mock_send.assert_not_called()
        mock_error.assert_called_once()


# ── process_badge_scan — QR code path ─────────────────────────────────────────

class TestQRScanCheckIn:

    @patch("receiver.send_typed_message")
    def test_qr_scan_sends_lease_request_on_entrance(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[_badge_partner()], True]
        receiver.process_badge_scan(_qr_root("entrance"), uid, models)
        mock_send.assert_called_once_with("wallet_lease_request", ANY)

    @patch("receiver.send_typed_message")
    def test_qr_scan_lease_request_has_no_badge_id(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[_badge_partner()], True]
        with patch("receiver.build_wallet_lease_request_xml") as mock_builder:
            mock_builder.return_value = "<xml/>"
            receiver.process_badge_scan(_qr_root("entrance"), uid, models)
        mock_builder.assert_called_once_with(identity_uuid=_UUID, badge_id=None)

    @patch("receiver.send_typed_message")
    def test_qr_bar_scan_triggers_lease(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[_badge_partner()], True]
        receiver.process_badge_scan(_qr_root("bar"), uid, models)
        mock_send.assert_called_once_with("wallet_lease_request", ANY)

    @patch("receiver.send_typed_message")
    def test_qr_session_scan_does_not_trigger_lease(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.return_value = [_badge_partner()]
        receiver.process_badge_scan(_qr_root("session"), uid, models)
        mock_send.assert_not_called()

    @patch("receiver.send_typed_message")
    def test_qr_scan_skips_if_lease_already_active(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.return_value = [_badge_partner(lease_active=True)]
        receiver.process_badge_scan(_qr_root("entrance"), uid, models)
        mock_send.assert_not_called()

    @patch("receiver.send_error_to_queue")
    @patch("receiver.send_typed_message")
    def test_qr_scan_sends_error_when_profile_not_found(self, mock_send, mock_error, odoo):
        uid, models = odoo
        models.execute_kw.return_value = []
        receiver.process_badge_scan(_qr_root("entrance"), uid, models)
        mock_send.assert_not_called()
        mock_error.assert_called_once()
        assert mock_error.call_args[1]["error_code"] == "profile_not_found"

    def test_qr_scan_raises_when_neither_id_present(self, odoo):
        uid, models = odoo
        root = ET.fromstring(
            "<message><header/>"
            "<body>"
            "<location>entrance</location>"
            "<scanned_at>2026-05-08T12:00:00Z</scanned_at>"
            "</body></message>"
        )
        with pytest.raises(ValueError, match="neither badge_id nor identity_uuid"):
            receiver.process_badge_scan(root, uid, models)


# ── _return_lease ──────────────────────────────────────────────────────────────

class TestReturnLease:

    def _fresh_partner(self) -> dict:
        return {
            "id": 99, "x_user_id": _UUID, "x_wallet_balance": 30.0,
            "x_lease_id": _LEASE, "x_lease_transaction_count": 5,
        }

    @patch("receiver.send_typed_message")
    def test_fetches_fresh_data_immediately_before_acting(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[self._fresh_partner()], True]
        receiver._return_lease(99, uid, models)
        first_call = models.execute_kw.call_args_list[0]
        assert first_call[0][4] == "search_read"
        assert first_call[0][5] == [[["id", "=", 99]]]

    @patch("receiver.send_typed_message")
    def test_write_happens_before_send(self, mock_send, odoo):
        """Odoo cleared before publishing to prevent duplicate returns on retry."""
        uid, models = odoo
        call_order = []

        def track_kw(*args):
            if args[4] == "search_read":
                return [self._fresh_partner()]
            call_order.append("write")
            return True

        mock_send.side_effect = lambda *a: call_order.append("send")
        models.execute_kw.side_effect = track_kw
        receiver._return_lease(99, uid, models)
        assert call_order == ["write", "send"]

    @patch("receiver.send_typed_message")
    def test_sends_fresh_balance_lease_id_and_tx_count(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[self._fresh_partner()], True]
        with patch("receiver.build_wallet_lease_return_xml") as mock_builder:
            mock_builder.return_value = "<xml/>"
            receiver._return_lease(99, uid, models)
        mock_builder.assert_called_once_with(
            identity_uuid=_UUID,
            final_balance=30.0,
            lease_id=_LEASE,
            transaction_count=5,
        )

    @patch("receiver.send_typed_message")
    def test_clears_all_lease_fields_in_odoo(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[self._fresh_partner()], True]
        receiver._return_lease(99, uid, models)
        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        assert vals == {"x_lease_active": False, "x_lease_id": "", "x_lease_transaction_count": 0}

    @patch("receiver.send_typed_message")
    def test_noop_if_partner_not_found(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.return_value = []
        receiver._return_lease(99, uid, models)
        mock_send.assert_not_called()
        assert models.execute_kw.call_count == 1  # only the search_read


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
        models.execute_kw.side_effect = [[self._partner()], 25.0, 1]
        receiver.process_wallet_remote_topup(_topup_root(_UUID, "5.0"), uid, models)
        second_call = models.execute_kw.call_args_list[1]
        assert second_call[0][3] == "pos.order"
        assert second_call[0][4] == "action_add_wallet_amount"
        assert second_call[0][5] == [7, 5.0]

    @patch("receiver.send_typed_message")
    def test_increments_lease_tx_count_after_topup(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[self._partner()], 25.0, 1]
        receiver.process_wallet_remote_topup(_topup_root(_UUID, "5.0"), uid, models)
        third_call = models.execute_kw.call_args_list[2]
        assert third_call[0][3] == "pos.order"
        assert third_call[0][4] == "action_increment_lease_tx_count"
        assert third_call[0][5] == [7]

    @patch("receiver.send_typed_message")
    def test_sends_balance_update_with_authority_kassa(self, mock_send, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[self._partner()], 25.0, 1]
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

    def test_raises_when_body_missing(self, odoo):
        uid, models = odoo
        root = ET.fromstring("<message><header/></message>")
        with pytest.raises(ValueError, match="<body> missing"):
            receiver.process_event_ended(root, uid, models)

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
