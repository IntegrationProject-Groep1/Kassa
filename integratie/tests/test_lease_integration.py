# test_lease_integration.py – Pipeline-level integration tests for the Authority Lease Model
#
# These tests exercise process_message() end-to-end including real XSD validation.
# The only mocked surfaces are Odoo XML-RPC and RabbitMQ publishing.

import uuid
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
def ch():
    m = MagicMock()
    m.delivery_tag = 99
    return m


@pytest.fixture
def method():
    m = MagicMock()
    m.delivery_tag = 99
    return m


# ── XML builders for inbound messages ─────────────────────────────────────────
# These produce XML that is fully valid against the XSD schemas so that
# process_message() does not reject them at the validation step.

def _make_id() -> str:
    return str(uuid.uuid4())


def _wallet_lease_grant_xml(
    identity_uuid: str,
    balance: float,
    lease_id: str,
    message_id: str | None = None,
) -> bytes:
    mid = message_id or _make_id()
    cid = _make_id()
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<message>"
        "<header>"
        f"<message_id>{mid}</message_id>"
        "<timestamp>2026-05-08T12:00:00Z</timestamp>"
        "<source>crm</source>"
        "<type>wallet_lease_grant</type>"
        "<version>2.0</version>"
        f"<correlation_id>{cid}</correlation_id>"
        "</header>"
        "<body>"
        f"<identity_uuid>{identity_uuid}</identity_uuid>"
        f'<current_balance currency="eur">{balance:.2f}</current_balance>'
        f"<lease_id>{lease_id}</lease_id>"
        "</body>"
        "</message>"
    ).encode("utf-8")


def _wallet_remote_topup_xml(
    identity_uuid: str,
    add_amount: float,
    reason: str = "online top-up",
    message_id: str | None = None,
) -> bytes:
    mid = message_id or _make_id()
    cid = _make_id()
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<message>"
        "<header>"
        f"<message_id>{mid}</message_id>"
        "<timestamp>2026-05-08T12:00:00Z</timestamp>"
        "<source>crm</source>"
        "<type>wallet_remote_topup</type>"
        "<version>2.0</version>"
        f"<correlation_id>{cid}</correlation_id>"
        "</header>"
        "<body>"
        f"<identity_uuid>{identity_uuid}</identity_uuid>"
        f'<add_amount currency="eur">{add_amount:.2f}</add_amount>'
        f"<reason>{reason}</reason>"
        "</body>"
        "</message>"
    ).encode("utf-8")


def _event_ended_xml(session_id: str = "SESSION-001", message_id: str | None = None) -> bytes:
    mid = message_id or _make_id()
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<message>"
        "<header>"
        f"<message_id>{mid}</message_id>"
        "<timestamp>2026-05-08T18:00:00Z</timestamp>"
        "<source>frontend</source>"
        "<type>event_ended</type>"
        "<version>2.0</version>"
        "</header>"
        "<body>"
        f"<session_id>{session_id}</session_id>"
        "<ended_at>2026-05-08T18:00:00Z</ended_at>"
        "</body>"
        "</message>"
    ).encode("utf-8")


# ── Helpers ────────────────────────────────────────────────────────────────────

_UUID = "550e8400-e29b-41d4-a716-446655440000"
_LEASE = "LEASE-XYZ"


def _odoo_mock(**kwargs):
    models = MagicMock()
    for attr, value in kwargs.items():
        setattr(models, attr, value)
    return 1, models


# ── wallet_lease_grant pipeline ────────────────────────────────────────────────

class TestWalletLeaseGrantPipeline:

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_valid_grant_passes_xsd_and_updates_odoo(self, mock_conn, mock_error, mock_send, ch, method):
        uid = 1
        models = MagicMock()
        models.execute_kw.side_effect = [[{"id": 10}], True]
        mock_conn.return_value = (uid, models)

        body = _wallet_lease_grant_xml(_UUID, 30.0, _LEASE)
        receiver.process_message(ch, method, None, body)

        mock_error.assert_not_called()
        ch.basic_nack.assert_not_called()
        ch.basic_ack.assert_called_once()

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        assert vals["x_wallet_balance"] == 30.0
        assert vals["x_lease_id"] == _LEASE
        assert vals["x_lease_active"] is True

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_invalid_grant_xml_rejected_before_odoo(self, mock_conn, mock_error, mock_send, ch, method):
        uid, models = 1, MagicMock()
        mock_conn.return_value = (uid, models)

        # Missing required correlation_id → XSD validation fails
        bad_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<message>"
            "<header>"
            f"<message_id>{_make_id()}</message_id>"
            "<timestamp>2026-05-08T12:00:00Z</timestamp>"
            "<source>crm</source>"
            "<type>wallet_lease_grant</type>"
            "<version>2.0</version>"
            # correlation_id is required — intentionally omitted
            "</header>"
            "<body>"
            f"<identity_uuid>{_UUID}</identity_uuid>"
            '<current_balance currency="eur">30.00</current_balance>'
            f"<lease_id>{_LEASE}</lease_id>"
            "</body>"
            "</message>"
        ).encode("utf-8")

        receiver.process_message(ch, method, None, bad_xml)

        ch.basic_nack.assert_called_once()
        mock_error.assert_called_once()
        models.execute_kw.assert_not_called()  # rejected before reaching Odoo


# ── wallet_remote_topup pipeline ───────────────────────────────────────────────

class TestWalletRemoteTopupPipeline:

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_valid_topup_passes_xsd_and_broadcasts(self, mock_conn, mock_error, mock_send, ch, method):
        uid = 1
        models = MagicMock()
        partner = {"id": 5, "x_wallet_balance": 20.0, "x_lease_active": True}
        models.execute_kw.side_effect = [[partner], 25.0]
        mock_conn.return_value = (uid, models)

        body = _wallet_remote_topup_xml(_UUID, 5.0)
        receiver.process_message(ch, method, None, body)

        mock_error.assert_not_called()
        ch.basic_nack.assert_not_called()
        ch.basic_ack.assert_called_once()

        # action_add_wallet_amount was called
        second_call = models.execute_kw.call_args_list[1]
        assert second_call[0][3] == "pos.order"
        assert second_call[0][4] == "action_add_wallet_amount"

        # wallet_balance_update was broadcast
        mock_send.assert_called_once_with("wallet_balance_update", ANY)

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_duplicate_topup_is_silently_skipped(self, mock_conn, mock_error, mock_send, ch, method):
        uid, models = 1, MagicMock()
        partner = {"id": 5, "x_wallet_balance": 20.0, "x_lease_active": True}
        models.execute_kw.side_effect = [[partner], 25.0, [partner], 25.0]
        mock_conn.return_value = (uid, models)

        mid = _make_id()
        body = _wallet_remote_topup_xml(_UUID, 5.0, message_id=mid)

        receiver.process_message(ch, method, None, body)
        receiver.process_message(ch, method, None, body)

        # Second delivery is deduplicated — action_add_wallet_amount called only once
        action_calls = [
            c for c in models.execute_kw.call_args_list
            if len(c[0]) > 4 and c[0][4] == "action_add_wallet_amount"
        ]
        assert len(action_calls) == 1


# ── event_ended pipeline ──────────────────────────────────────────────────────

class TestEventEndedPipeline:

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_valid_event_ended_passes_xsd_and_returns_all_leases(
        self, mock_conn, mock_error, mock_send, ch, method
    ):
        uid = 1
        models = MagicMock()
        active_partners = [
            {"id": 1, "x_user_id": _UUID, "x_wallet_balance": 10.0,
             "x_lease_id": "L1", "x_lease_transaction_count": 2},
            {"id": 2, "x_user_id": "550e8400-e29b-41d4-a716-446655440001",
             "x_wallet_balance": 5.0, "x_lease_id": "L2", "x_lease_transaction_count": 0},
        ]
        models.execute_kw.side_effect = [active_partners, True]
        mock_conn.return_value = (uid, models)

        body = _event_ended_xml()
        receiver.process_message(ch, method, None, body)

        mock_error.assert_not_called()
        ch.basic_nack.assert_not_called()
        ch.basic_ack.assert_called_once()

        assert mock_send.call_count == 2
        assert all(c[0][0] == "wallet_lease_return" for c in mock_send.call_args_list)

        write_call = models.execute_kw.call_args_list[1]
        assert set(write_call[0][5][0]) == {1, 2}
