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


def _badge_scanned_badge_xml(
    badge_id: str,
    location: str = "entrance",
    message_id: str | None = None,
) -> bytes:
    mid = message_id or _make_id()
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<message>"
        "<header>"
        f"<message_id>{mid}</message_id>"
        "<timestamp>2026-05-08T12:00:00Z</timestamp>"
        "<source>iot_gateway</source>"
        "<type>badge_scanned</type>"
        "<version>2.0</version>"
        "</header>"
        "<body>"
        f"<badge_id>{badge_id}</badge_id>"
        f"<location>{location}</location>"
        "<scanned_at>2026-05-08T12:00:00Z</scanned_at>"
        "</body>"
        "</message>"
    ).encode("utf-8")


def _badge_scanned_qr_xml(
    identity_uuid: str,
    location: str = "entrance",
    message_id: str | None = None,
) -> bytes:
    mid = message_id or _make_id()
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<message>"
        "<header>"
        f"<message_id>{mid}</message_id>"
        "<timestamp>2026-05-08T12:00:00Z</timestamp>"
        "<source>iot_gateway</source>"
        "<type>badge_scanned</type>"
        "<version>2.0</version>"
        "</header>"
        "<body>"
        f"<identity_uuid>{identity_uuid}</identity_uuid>"
        f"<location>{location}</location>"
        "<scanned_at>2026-05-08T12:00:00Z</scanned_at>"
        "</body>"
        "</message>"
    ).encode("utf-8")


def _partner(
    identity_uuid: str = _UUID,
    lease_active: bool = False,
    odoo_id: int = 10,
) -> dict:
    return {
        "id": odoo_id, "name": "Alice",
        "x_user_id": identity_uuid,
        "x_wallet_balance": 25.0, "x_date_of_birth": False,
        "is_company": False, "x_lease_active": lease_active,
        "x_lease_id": "LEASE-X" if lease_active else "",
        "x_lease_transaction_count": 2 if lease_active else 0,
    }


# ── badge_scanned badge path pipeline ─────────────────────────────────────────

class TestBadgeScanBadgePipeline:

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_entrance_sends_lease_request(self, mock_conn, mock_error, mock_send, ch, method):
        models = MagicMock()
        models.execute_kw.side_effect = [[_partner()], True]
        mock_conn.return_value = (1, models)

        receiver.process_message(ch, method, None, _badge_scanned_badge_xml("BADGE-001", "entrance"))

        mock_error.assert_not_called()
        ch.basic_nack.assert_not_called()
        ch.basic_ack.assert_called_once()
        mock_send.assert_called_once()
        assert mock_send.call_args[0][0] == "wallet_lease_request"

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_badge_lease_request_contains_badge_id(self, mock_conn, mock_error, mock_send, ch, method):
        models = MagicMock()
        models.execute_kw.side_effect = [[_partner()], True]
        mock_conn.return_value = (1, models)

        receiver.process_message(ch, method, None, _badge_scanned_badge_xml("BADGE-001", "entrance"))

        lease_xml = mock_send.call_args[0][1]
        assert "<badge_id>BADGE-001</badge_id>" in lease_xml

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_badge_not_found_sends_system_error_and_acks(self, mock_conn, mock_error, mock_send, ch, method):
        models = MagicMock()
        models.execute_kw.return_value = []
        mock_conn.return_value = (1, models)

        receiver.process_message(ch, method, None, _badge_scanned_badge_xml("UNKNOWN", "entrance"))

        mock_error.assert_called_once()
        assert mock_error.call_args[1]["error_code"] == "badge_not_found"
        mock_send.assert_not_called()
        ch.basic_ack.assert_called_once()

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_bar_scan_sends_lease_request(self, mock_conn, mock_error, mock_send, ch, method):
        models = MagicMock()
        models.execute_kw.side_effect = [[_partner()], True]
        mock_conn.return_value = (1, models)

        receiver.process_message(ch, method, None, _badge_scanned_badge_xml("BADGE-001", "bar"))

        mock_send.assert_called_once()
        assert mock_send.call_args[0][0] == "wallet_lease_request"
        mock_error.assert_not_called()
        ch.basic_ack.assert_called_once()

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_session_location_sends_lease_and_sessions_request(self, mock_conn, mock_error, mock_send, ch, method):
        models = MagicMock()
        models.execute_kw.side_effect = [[_partner()], True]
        mock_conn.return_value = (1, models)

        receiver.process_message(ch, method, None, _badge_scanned_badge_xml("BADGE-001", "session"))

        assert mock_send.call_count == 2
        msg_types = [c[0][0] for c in mock_send.call_args_list]
        assert "wallet_lease_request" in msg_types
        assert "user_sessions_request" in msg_types
        mock_error.assert_not_called()
        ch.basic_ack.assert_called_once()

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_invalid_xsd_nacks_and_sends_error(self, mock_conn, mock_error, mock_send, ch, method):
        mock_conn.return_value = (1, MagicMock())

        # Neither badge_id nor identity_uuid → xs:choice unsatisfied → XSD rejects
        bad_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<message><header>"
            f"<message_id>{_make_id()}</message_id>"
            "<timestamp>2026-05-08T12:00:00Z</timestamp>"
            "<source>iot_gateway</source>"
            "<type>badge_scanned</type>"
            "<version>2.0</version>"
            "</header>"
            "<body>"
            "<location>entrance</location>"
            "<scanned_at>2026-05-08T12:00:00Z</scanned_at>"
            "</body></message>"
        ).encode("utf-8")

        receiver.process_message(ch, method, None, bad_xml)

        ch.basic_nack.assert_called_once()
        mock_error.assert_called_once()
        mock_conn.return_value[1].execute_kw.assert_not_called()


# ── badge_scanned QR path pipeline ────────────────────────────────────────────

class TestBadgeScanQRPipeline:

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_entrance_sends_lease_request(self, mock_conn, mock_error, mock_send, ch, method):
        models = MagicMock()
        models.execute_kw.side_effect = [[_partner()], True]
        mock_conn.return_value = (1, models)

        receiver.process_message(ch, method, None, _badge_scanned_qr_xml(_UUID, "entrance"))

        mock_error.assert_not_called()
        ch.basic_nack.assert_not_called()
        ch.basic_ack.assert_called_once()
        mock_send.assert_called_once()
        assert mock_send.call_args[0][0] == "wallet_lease_request"

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_qr_lease_request_omits_badge_id(self, mock_conn, mock_error, mock_send, ch, method):
        models = MagicMock()
        models.execute_kw.side_effect = [[_partner()], True]
        mock_conn.return_value = (1, models)

        receiver.process_message(ch, method, None, _badge_scanned_qr_xml(_UUID, "entrance"))

        lease_xml = mock_send.call_args[0][1]
        assert "<badge_id>" not in lease_xml
        assert f"<identity_uuid>{_UUID}</identity_uuid>" in lease_xml

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_qr_lease_request_passes_outgoing_xsd(self, mock_conn, mock_error, mock_send, ch, method):
        """wallet_lease_request emitted on QR scan must validate against outgoing XSD."""
        from pathlib import Path
        from lxml import etree

        models = MagicMock()
        models.execute_kw.side_effect = [[_partner()], True]
        mock_conn.return_value = (1, models)

        captured: dict = {}
        mock_send.side_effect = lambda t, x, **kw: captured.update({"type": t, "xml": x})

        receiver.process_message(ch, method, None, _badge_scanned_qr_xml(_UUID, "entrance"))

        assert captured.get("type") == "wallet_lease_request"
        schema_path = Path(receiver.__file__).parent / "schemas" / "schema_wallet_lease_request.xsd"
        parser = etree.XMLParser(resolve_entities=False, dtd_validation=False, no_network=True)
        schema = etree.XMLSchema(etree.parse(str(schema_path), parser))
        doc = etree.fromstring(captured["xml"].encode("utf-8"), parser=parser)
        assert schema.validate(doc), f"wallet_lease_request XSD failed: {schema.error_log}"

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_profile_not_found_sends_system_error_and_acks(self, mock_conn, mock_error, mock_send, ch, method):
        models = MagicMock()
        models.execute_kw.return_value = []
        mock_conn.return_value = (1, models)

        receiver.process_message(ch, method, None, _badge_scanned_qr_xml(_UUID, "entrance"))

        mock_error.assert_called_once()
        assert mock_error.call_args[1]["error_code"] == "profile_not_found"
        mock_send.assert_not_called()
        ch.basic_ack.assert_called_once()

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_bar_scan_sends_lease_request(self, mock_conn, mock_error, mock_send, ch, method):
        models = MagicMock()
        models.execute_kw.side_effect = [[_partner()], True]
        mock_conn.return_value = (1, models)

        receiver.process_message(ch, method, None, _badge_scanned_qr_xml(_UUID, "bar"))

        mock_send.assert_called_once()
        assert mock_send.call_args[0][0] == "wallet_lease_request"
        mock_error.assert_not_called()
        ch.basic_ack.assert_called_once()

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_session_location_sends_lease_and_sessions_request(self, mock_conn, mock_error, mock_send, ch, method):
        models = MagicMock()
        models.execute_kw.side_effect = [[_partner()], True]
        mock_conn.return_value = (1, models)

        receiver.process_message(ch, method, None, _badge_scanned_qr_xml(_UUID, "session"))

        assert mock_send.call_count == 2
        msg_types = [c[0][0] for c in mock_send.call_args_list]
        assert "wallet_lease_request" in msg_types
        assert "user_sessions_request" in msg_types
        mock_error.assert_not_called()
        ch.basic_ack.assert_called_once()

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_lease_already_active_skips_without_error(self, mock_conn, mock_error, mock_send, ch, method):
        models = MagicMock()
        models.execute_kw.return_value = [_partner(lease_active=True)]
        mock_conn.return_value = (1, models)

        receiver.process_message(ch, method, None, _badge_scanned_qr_xml(_UUID, "entrance"))

        mock_send.assert_not_called()
        mock_error.assert_not_called()
        ch.basic_ack.assert_called_once()

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_odoo_looked_up_by_identity_uuid_not_badge_id(self, mock_conn, mock_error, mock_send, ch, method):
        """QR path must query x_user_id, not x_badge_id."""
        models = MagicMock()
        models.execute_kw.side_effect = [[_partner()], True]
        mock_conn.return_value = (1, models)

        receiver.process_message(ch, method, None, _badge_scanned_qr_xml(_UUID, "entrance"))

        search_call = models.execute_kw.call_args_list[0]
        domain = search_call[0][5][0]
        assert domain[0][0] == "x_user_id"
        assert domain[0][2] == _UUID


# ── wallet_lease_grant pipeline ────────────────────────────────────────────────

class TestWalletLeaseGrantPipeline:

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_valid_grant_passes_xsd_and_updates_odoo(self, mock_conn, mock_error, mock_send, ch, method):
        uid = 1
        models = MagicMock()
        # search_read now returns x_pending_topup_balance too
        models.execute_kw.side_effect = [
            [{"id": 10, "name": "Alice", "x_payment_status": "unpaid",
              "x_outstanding_amount": 0.0, "x_pending_topup_balance": 0.0}],
            True,   # write
            True,   # _publish_partner_bus_event
        ]
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
        assert vals["x_pending_topup_balance"] == 0.0  # cleared

        # wallet_balance_update sent to external frontend
        assert mock_send.call_count >= 1
        types = [c[0][0] for c in mock_send.call_args_list]
        assert "wallet_balance_update" in types

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_grant_merges_pending_topup_with_crm_balance(
            self, mock_conn, mock_error, mock_send, ch, method):
        """Pending top-up parked before lease grant is merged into final balance.

        Scenario: visitor scanned → lease requested → cashier did €20 top-up
        (parked in x_pending_topup_balance) → CRM grants lease with balance €50.
        Final balance must be €70 (not €50).
        """
        uid = 1
        models = MagicMock()
        models.execute_kw.side_effect = [
            [{"id": 10, "name": "Alice", "x_payment_status": "unpaid",
              "x_outstanding_amount": 0.0, "x_pending_topup_balance": 20.0}],  # pending!
            True,   # write
            True,   # _publish_partner_bus_event
        ]
        mock_conn.return_value = (uid, models)

        body = _wallet_lease_grant_xml(_UUID, 50.0, _LEASE)
        receiver.process_message(ch, method, None, body)

        mock_error.assert_not_called()
        ch.basic_ack.assert_called_once()

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        # final balance = CRM (50) + pending (20) = 70
        assert vals["x_wallet_balance"] == 70.0, (
            "Pending top-up must be merged with CRM balance on lease grant"
        )
        assert vals["x_pending_topup_balance"] == 0.0, "Pending field must be cleared after merge"

        # wallet_balance_update sent with the correct merged balance
        update_calls = [c for c in mock_send.call_args_list
                        if c[0][0] == "wallet_balance_update"]
        assert len(update_calls) == 1
        wallet_xml = update_calls[0][0][1]
        assert "70" in wallet_xml, "wallet_balance_update XML must reflect merged balance of 70"

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
        partner = {
            "id": 5, "x_wallet_balance": 20.0, "x_lease_active": True,
            "x_lease_id": "LSE-001", "x_pending_topup_balance": 0.0,
            "x_outstanding_amount": 0.0, "x_payment_status": "paid", "name": "Visitor",
        }
        models.execute_kw.side_effect = [[partner], 25.0, 1, True]
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

        # action_increment_lease_tx_count was called after
        third_call = models.execute_kw.call_args_list[2]
        assert third_call[0][4] == "action_increment_lease_tx_count"

        # wallet_balance_update was broadcast
        mock_send.assert_called_once_with("wallet_balance_update", ANY)

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_duplicate_topup_is_silently_skipped(self, mock_conn, mock_error, mock_send, ch, method):
        uid, models = 1, MagicMock()
        partner = {
            "id": 5, "x_wallet_balance": 20.0, "x_lease_active": True,
            "x_lease_id": "LSE-001", "x_pending_topup_balance": 0.0,
            "x_outstanding_amount": 0.0, "x_payment_status": "paid", "name": "Visitor",
        }
        models.execute_kw.side_effect = [[partner], 25.0, 1, True]
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
    def test_valid_event_ended_passes_xsd_and_acks(
        self, mock_conn, mock_error, mock_send, ch, method
    ):
        """XSD-valid event_ended is accepted (acked) without errors."""
        uid = 1
        models = MagicMock()
        mock_conn.return_value = (uid, models)

        body = _event_ended_xml()
        receiver.process_message(ch, method, None, body)

        mock_error.assert_not_called()
        ch.basic_nack.assert_not_called()
        ch.basic_ack.assert_called_once()

    @patch("receiver.send_typed_message")
    def test_do_return_all_leases_returns_all_active_leases(self, mock_send):
        """_do_return_all_leases sends wallet_lease_return for every active partner."""
        uid = 1
        models = MagicMock()
        active_partners = [
            {"id": 1, "x_user_id": _UUID, "x_wallet_balance": 10.0,
             "x_lease_id": "L1", "x_lease_transaction_count": 2},
            {"id": 2, "x_user_id": "550e8400-e29b-41d4-a716-446655440001",
             "x_wallet_balance": 5.0, "x_lease_id": "L2", "x_lease_transaction_count": 0},
        ]
        models.execute_kw.side_effect = [active_partners, True]

        receiver._do_return_all_leases(uid, models)

        assert mock_send.call_count == 2
        assert all(c[0][0] == "wallet_lease_return" for c in mock_send.call_args_list)

        write_call = models.execute_kw.call_args_list[1]
        assert set(write_call[0][5][0]) == {1, 2}
