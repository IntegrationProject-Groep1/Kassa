# test_frontend_session_flow.py
# Tests for the Frontend session architecture:
#   - QR scan RPC routes to kassa.exchange (not planning.exchange)
#   - XSD validation of session_created / session_updated / session_deleted
#   - process_session_created / process_session_updated / process_session_deleted handlers
#   - RabbitMQ binding verification for start_listening()
#
# Run with: pytest tests/test_frontend_session_flow.py -v

import json
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import pytest

import receiver


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_cache():
    receiver.seen_message_ids.clear()
    yield
    receiver.seen_message_ids.clear()


@pytest.fixture
def odoo():
    return 1, MagicMock()


@pytest.fixture
def ch():
    return MagicMock()


@pytest.fixture
def method():
    m = MagicMock()
    m.delivery_tag = 42
    return m


# ── XML helpers ────────────────────────────────────────────────────────────────

_UUID = "550e8400-e29b-41d4-a716-446655440000"
_UUID2 = "660e8400-e29b-41d4-a716-446655440000"

_VALID_MSG_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_VALID_IDENTITY = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"
_VALID_SESSION_ID = "sess-0001"


def _session_created_xml(
    message_id=_VALID_MSG_ID,
    identity_uuid=_VALID_IDENTITY,
    session_id=_VALID_SESSION_ID,
    title="Workshop Python",
    price=None,
):
    price_el = f'<price currency="eur">{price}</price>' if price is not None else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<message>"
        "<header>"
        f"<message_id>{message_id}</message_id>"
        "<timestamp>2026-05-14T12:00:00Z</timestamp>"
        "<source>frontend</source>"
        "<type>session_created</type>"
        "<version>2.0</version>"
        "</header>"
        "<body>"
        f"<identity_uuid>{identity_uuid}</identity_uuid>"
        "<session>"
        f"<session_id>{session_id}</session_id>"
        f"<title>{title}</title>"
        f"{price_el}"
        "</session>"
        "</body>"
        "</message>"
    )


def _session_updated_xml(
    message_id=_VALID_MSG_ID,
    identity_uuid=_VALID_IDENTITY,
    session_id=_VALID_SESSION_ID,
    title="Workshop Python Updated",
    price=None,
):
    price_el = f'<price currency="eur">{price}</price>' if price is not None else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<message>"
        "<header>"
        f"<message_id>{message_id}</message_id>"
        "<timestamp>2026-05-14T12:00:00Z</timestamp>"
        "<source>frontend</source>"
        "<type>session_updated</type>"
        "<version>2.0</version>"
        "</header>"
        "<body>"
        f"<identity_uuid>{identity_uuid}</identity_uuid>"
        "<session>"
        f"<session_id>{session_id}</session_id>"
        f"<title>{title}</title>"
        f"{price_el}"
        "</session>"
        "</body>"
        "</message>"
    )


def _session_deleted_xml(
    message_id=_VALID_MSG_ID,
    identity_uuid=_VALID_IDENTITY,
    session_id=_VALID_SESSION_ID,
    reason=None,
):
    reason_el = f"<reason>{reason}</reason>" if reason else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<message>"
        "<header>"
        f"<message_id>{message_id}</message_id>"
        "<timestamp>2026-05-14T12:00:00Z</timestamp>"
        "<source>frontend</source>"
        "<type>session_deleted</type>"
        "<version>2.0</version>"
        "</header>"
        "<body>"
        f"<identity_uuid>{identity_uuid}</identity_uuid>"
        f"<session_id>{session_id}</session_id>"
        f"{reason_el}"
        "</body>"
        "</message>"
    )


def _root_from_xml(xml_str):
    return ET.fromstring(xml_str)


# ── XSD validation ─────────────────────────────────────────────────────────────

class TestSessionXsdValidation:
    def test_session_created_valid_without_price(self):
        receiver.validate_xml(_session_created_xml(), "session_created")

    def test_session_created_valid_with_price(self):
        receiver.validate_xml(_session_created_xml(price=25.0), "session_created")

    def test_session_created_invalid_missing_title(self):
        xml = _session_created_xml().replace(
            "<title>Workshop Python</title>", ""
        )
        with pytest.raises(ValueError, match="XSD validation failed"):
            receiver.validate_xml(xml, "session_created")

    def test_session_created_wrong_source_rejected(self):
        xml = _session_created_xml().replace("<source>frontend</source>", "<source>crm</source>")
        with pytest.raises(ValueError, match="XSD validation failed"):
            receiver.validate_xml(xml, "session_created")

    def test_session_updated_valid_without_price(self):
        receiver.validate_xml(_session_updated_xml(), "session_updated")

    def test_session_updated_valid_with_price(self):
        receiver.validate_xml(_session_updated_xml(price=30.0), "session_updated")

    def test_session_updated_invalid_missing_session(self):
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<message>"
            "<header>"
            f"<message_id>{_VALID_MSG_ID}</message_id>"
            "<timestamp>2026-05-14T12:00:00Z</timestamp>"
            "<source>frontend</source>"
            "<type>session_updated</type>"
            "<version>2.0</version>"
            "</header>"
            "<body>"
            f"<identity_uuid>{_VALID_IDENTITY}</identity_uuid>"
            "</body>"
            "</message>"
        )
        with pytest.raises(ValueError, match="XSD validation failed"):
            receiver.validate_xml(xml, "session_updated")

    def test_session_deleted_valid_without_reason(self):
        receiver.validate_xml(_session_deleted_xml(), "session_deleted")

    def test_session_deleted_valid_with_reason(self):
        receiver.validate_xml(_session_deleted_xml(reason="Cancelled by admin"), "session_deleted")

    def test_session_deleted_invalid_missing_session_id(self):
        xml = _session_deleted_xml().replace(f"<session_id>{_VALID_SESSION_ID}</session_id>", "")
        with pytest.raises(ValueError, match="XSD validation failed"):
            receiver.validate_xml(xml, "session_deleted")

    def test_user_sessions_response_accepts_frontend_source(self):
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<message>"
            "<header>"
            f"<message_id>{_VALID_MSG_ID}</message_id>"
            "<timestamp>2026-05-14T12:00:00Z</timestamp>"
            "<source>frontend</source>"
            "<type>user_sessions_response</type>"
            "<version>2.0</version>"
            f"<correlation_id>{_UUID}</correlation_id>"
            "</header>"
            "<body>"
            f"<identity_uuid>{_VALID_IDENTITY}</identity_uuid>"
            "<status>ok</status>"
            "<session_count>0</session_count>"
            "<sessions/>"
            "</body>"
            "</message>"
        )
        receiver.validate_xml(xml, "user_sessions_response")

    def test_user_sessions_response_still_accepts_planning_source(self):
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<message>"
            "<header>"
            f"<message_id>{_VALID_MSG_ID}</message_id>"
            "<timestamp>2026-05-14T12:00:00Z</timestamp>"
            "<source>planning</source>"
            "<type>user_sessions_response</type>"
            "<version>2.0</version>"
            f"<correlation_id>{_UUID}</correlation_id>"
            "</header>"
            "<body>"
            f"<identity_uuid>{_VALID_IDENTITY}</identity_uuid>"
            "<status>ok</status>"
            "<session_count>0</session_count>"
            "<sessions/>"
            "</body>"
            "</message>"
        )
        receiver.validate_xml(xml, "user_sessions_response")


# ── process_session_created ────────────────────────────────────────────────────

class TestProcessSessionCreated:

    def _root(self, **kwargs):
        return _root_from_xml(_session_created_xml(**kwargs))

    def _partner(self, session_title="[]", outstanding=0.0, status="unpaid"):
        return {
            "id": 5,
            "name": "Alice",
            "x_session_title": session_title,
            "x_outstanding_amount": outstanding,
            "x_payment_status": status,
        }

    def test_appends_new_session_when_partner_found(self, odoo):
        uid, models = odoo
        # partner found; write x_session_title; product not found; category found; create product; bus event
        models.execute_kw.side_effect = [
            [self._partner()],        # res.partner search_read
            True,                     # res.partner write
            [],                       # product.template search_read (not found)
            [{"id": 3}],              # pos.category search_read
            1,                        # product.template create
            True,                     # pos.order send_partner_bus_event
        ]
        receiver.process_session_created(self._root(title="Workshop Python", session_id="s1"), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        assert write_call[0][3] == "res.partner"
        assert write_call[0][4] == "write"
        written_val = write_call[0][5][1]["x_session_title"]
        sessions = json.loads(written_val)
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "s1"
        assert sessions[0]["title"] == "Workshop Python"

    def test_is_idempotent_on_duplicate_session_id(self, odoo):
        uid, models = odoo
        existing_sessions = json.dumps([{"session_id": "s1", "title": "Workshop Python", "price": None}])
        models.execute_kw.side_effect = [
            [self._partner(session_title=existing_sessions)],  # partner found with s1 already
            [],                         # product.template search_read (ensure_session_product)
            [{"id": 3}],                # pos.category search_read
            1,                          # product.template create
            True,                       # bus event
        ]
        receiver.process_session_created(self._root(session_id="s1"), uid, models)

        # Should NOT have called write on res.partner (no duplicate)
        all_calls = models.execute_kw.call_args_list
        partner_writes = [c for c in all_calls if c[0][3] == "res.partner" and c[0][4] == "write"]
        assert len(partner_writes) == 0

    def test_partner_not_found_acks_without_write(self, odoo):
        uid, models = odoo
        models.execute_kw.return_value = []  # partner not found

        receiver.process_session_created(self._root(), uid, models)

        # Only 1 execute_kw call (search_read); no write, no product, no bus event
        assert models.execute_kw.call_count == 1

    def test_price_stored_in_session_entry(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [self._partner()],
            True,
            [{"id": 7, "list_price": 0.0}],  # product exists, price differs
            True,                              # product write price
            True,                             # bus event
        ]
        receiver.process_session_created(self._root(price=25.0), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        sessions = json.loads(write_call[0][5][1]["x_session_title"])
        assert sessions[0]["price"] == 25.0

    def test_bus_event_published_after_write(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [self._partner()],
            True,
            [],
            [{"id": 3}],
            1,
            True,
        ]
        receiver.process_session_created(self._root(), uid, models)

        bus_call = models.execute_kw.call_args_list[-1]
        assert bus_call[0][3] == "pos.order"
        assert bus_call[0][4] == "send_partner_bus_event"

    def test_normalises_legacy_string_entries(self, odoo):
        uid, models = odoo
        # Old plain-string format in x_session_title
        models.execute_kw.side_effect = [
            [self._partner(session_title='["Old Session"]')],
            True,
            [],
            [{"id": 3}],
            1,
            True,
        ]
        receiver.process_session_created(self._root(session_id="s2", title="New Session"), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        sessions = json.loads(write_call[0][5][1]["x_session_title"])
        # Old string entry normalised + new entry appended
        assert len(sessions) == 2
        assert any(s.get("session_id") == "s2" for s in sessions)


# ── process_session_updated ────────────────────────────────────────────────────

class TestProcessSessionUpdated:

    def _root(self, **kwargs):
        return _root_from_xml(_session_updated_xml(**kwargs))

    def _partner_with_session(self, session_id="s1", title="Old Title", price=10.0):
        sessions = json.dumps([{"session_id": session_id, "title": title, "price": price}])
        return {
            "id": 5,
            "name": "Alice",
            "x_session_title": sessions,
            "x_outstanding_amount": 10.0,
            "x_payment_status": "unpaid",
        }

    def test_updates_existing_session_by_id(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [self._partner_with_session(session_id="s1", title="Old Title")],
            True,                           # write partner
            [{"id": 7, "list_price": 10.0}],  # product found
            True,                           # product write price
            True,                           # bus event
        ]
        receiver.process_session_updated(
            self._root(session_id="s1", title="New Title", price=20.0), uid, models
        )

        write_call = models.execute_kw.call_args_list[1]
        sessions = json.loads(write_call[0][5][1]["x_session_title"])
        assert sessions[0]["session_id"] == "s1"
        assert sessions[0]["title"] == "New Title"
        assert sessions[0]["price"] == 20.0

    def test_upserts_when_session_id_not_found(self, odoo):
        uid, models = odoo
        # Partner exists but doesn't have session_id "s99"
        models.execute_kw.side_effect = [
            [self._partner_with_session(session_id="s1")],
            True,   # write partner (upsert)
            [],     # product not found
            [],     # category not found
            1,      # product create
            True,   # bus event
        ]
        receiver.process_session_updated(
            self._root(session_id="s99", title="Brand New"), uid, models
        )

        write_call = models.execute_kw.call_args_list[1]
        sessions = json.loads(write_call[0][5][1]["x_session_title"])
        assert len(sessions) == 2
        assert any(s["session_id"] == "s99" for s in sessions)

    def test_partner_not_found_acks_without_write(self, odoo):
        uid, models = odoo
        models.execute_kw.return_value = []

        receiver.process_session_updated(self._root(), uid, models)

        assert models.execute_kw.call_count == 1

    def test_bus_event_published(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [self._partner_with_session()],
            True,
            [{"id": 7, "list_price": 10.0}],
            True,
            True,
        ]
        receiver.process_session_updated(self._root(price=15.0), uid, models)

        bus_call = models.execute_kw.call_args_list[-1]
        assert bus_call[0][3] == "pos.order"
        assert bus_call[0][4] == "send_partner_bus_event"


# ── process_session_deleted ────────────────────────────────────────────────────

class TestProcessSessionDeleted:

    def _root(self, **kwargs):
        return _root_from_xml(_session_deleted_xml(**kwargs))

    def _partner_with_two_sessions(self):
        sessions = json.dumps([
            {"session_id": "s1", "title": "Session A", "price": None},
            {"session_id": "s2", "title": "Session B", "price": None},
        ])
        return {
            "id": 5,
            "name": "Alice",
            "x_session_title": sessions,
            "x_outstanding_amount": 0.0,
            "x_payment_status": "unpaid",
        }

    def test_removes_matching_session_id(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [self._partner_with_two_sessions()],
            True,    # write
            True,    # bus event
        ]
        receiver.process_session_deleted(self._root(session_id="s1"), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        sessions = json.loads(write_call[0][5][1]["x_session_title"])
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "s2"

    def test_noop_when_session_id_not_found(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [self._partner_with_two_sessions()],
            True,    # bus event (no write)
        ]
        receiver.process_session_deleted(self._root(session_id="s99"), uid, models)

        # Write should NOT have been called
        all_calls = models.execute_kw.call_args_list
        partner_writes = [c for c in all_calls if c[0][3] == "res.partner" and c[0][4] == "write"]
        assert len(partner_writes) == 0

    def test_partner_not_found_acks_without_write(self, odoo):
        uid, models = odoo
        models.execute_kw.return_value = []

        receiver.process_session_deleted(self._root(), uid, models)

        assert models.execute_kw.call_count == 1

    def test_does_not_delete_pos_product(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [self._partner_with_two_sessions()],
            True,
            True,
        ]
        receiver.process_session_deleted(self._root(session_id="s1"), uid, models)

        # No call to product.template unlink
        all_calls = models.execute_kw.call_args_list
        product_deletes = [
            c for c in all_calls
            if c[0][3] == "product.template" and c[0][4] in ("unlink", "write")
        ]
        assert len(product_deletes) == 0

    def test_bus_event_published_after_delete(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [self._partner_with_two_sessions()],
            True,
            True,
        ]
        receiver.process_session_deleted(self._root(session_id="s1"), uid, models)

        bus_call = models.execute_kw.call_args_list[-1]
        assert bus_call[0][3] == "pos.order"
        assert bus_call[0][4] == "send_partner_bus_event"


# ── QR scan routing ────────────────────────────────────────────────────────────

class TestQrScanRouting:
    """Verify _fetch_sessions_from_frontend sends to kassa.exchange, not planning.exchange."""

    def test_qr_scan_controller_uses_kassa_exchange_not_planning(self):
        """
        Verify the QR controller source uses kassa.exchange and
        frontend routing key, not planning.exchange.
        The Odoo addon cannot be imported in the test env, so we check
        the source file directly.
        """
        import os
        controller_path = os.path.join(
            os.path.dirname(__file__), "..", "..",
            "addons", "kassa_pos_custom", "controllers", "main.py"
        )
        with open(controller_path) as f:
            source = f.read()

        assert "planning.exchange" not in source, \
            "planning.exchange must be removed from the QR controller"
        assert "kassa.to.frontend.user_sessions_request" in source, \
            "QR controller must use frontend routing key"
        assert "_fetch_sessions_from_frontend" in source, \
            "Function must be renamed to _fetch_sessions_from_frontend"
        assert "planning.exchange" not in source, \
            "RABBIT_PLANNING_EXCHANGE must not be used"
        assert 'RABBIT_EXCHANGE' in source, \
            "Should use RABBIT_EXCHANGE env var for kassa.exchange"


# ── RabbitMQ binding verification ─────────────────────────────────────────────

class TestReceiverBindings:
    """Verify start_listening() binds the correct Frontend routing keys."""

    @patch("receiver.connect_to_rabbitmq")
    @patch("receiver.setup_exchange")
    @patch("receiver.flush_buffer")
    def test_binds_frontend_session_routing_keys(self, mock_flush, mock_setup, mock_connect):
        mock_flush.return_value = []
        conn_mock = MagicMock()
        channel_mock = MagicMock()
        conn_mock.channel.return_value = channel_mock
        mock_connect.return_value = conn_mock

        # Interrupt start_consuming so the test doesn't hang
        channel_mock.start_consuming.side_effect = KeyboardInterrupt()

        try:
            receiver.start_listening()
        except KeyboardInterrupt:
            pass

        bound_routing_keys = [
            call_args[1].get("routing_key") or (call_args[0][2] if len(call_args[0]) > 2 else None)
            for call_args in channel_mock.queue_bind.call_args_list
        ]

        expected_keys = {
            "frontend.to.kassa.user_sessions_response",
            "frontend.to.kassa.session.created",
            "frontend.to.kassa.session.updated",
            "frontend.to.kassa.session.deleted",
        }
        for key in expected_keys:
            assert key in bound_routing_keys, f"Missing binding: {key}"

    @patch("receiver.connect_to_rabbitmq")
    @patch("receiver.setup_exchange")
    @patch("receiver.flush_buffer")
    def test_does_not_bind_planning_routing_keys(self, mock_flush, mock_setup, mock_connect):
        mock_flush.return_value = []
        conn_mock = MagicMock()
        channel_mock = MagicMock()
        conn_mock.channel.return_value = channel_mock
        mock_connect.return_value = conn_mock
        channel_mock.start_consuming.side_effect = KeyboardInterrupt()

        try:
            receiver.start_listening()
        except KeyboardInterrupt:
            pass

        bound_routing_keys = [
            call_args[1].get("routing_key") or (call_args[0][2] if len(call_args[0]) > 2 else None)
            for call_args in channel_mock.queue_bind.call_args_list
        ]

        forbidden = [
            "planning.to.kassa.user_sessions_response",
            "planning.to.kassa.session.view.response",
        ]
        for key in forbidden:
            assert key not in bound_routing_keys, f"Should NOT be bound: {key}"


# ── process_message integration for session types ─────────────────────────────

class TestProcessMessageSessionTypes:
    """Verify process_message dispatches to the 3 new handlers correctly."""

    def _frontend_xml_bytes(self, msg_type, body_xml, message_id=_VALID_MSG_ID):
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<message>"
            "<header>"
            f"<message_id>{message_id}</message_id>"
            f"<type>{msg_type}</type>"
            "<source>frontend</source>"
            "<timestamp>2026-05-14T12:00:00Z</timestamp>"
            "<version>2.0</version>"
            "</header>"
            f"<body>{body_xml}</body>"
            "</message>"
        ).encode("utf-8")

    @patch("receiver.get_odoo_connection")
    @patch("receiver.validate_xml")
    def test_session_created_dispatched_and_acked(self, mock_validate, mock_odoo, ch, method):
        uid, models = 1, MagicMock()
        mock_odoo.return_value = (uid, models)
        # partner not found → handler returns early without write
        models.execute_kw.return_value = []

        body_xml = (
            f"<identity_uuid>{_VALID_IDENTITY}</identity_uuid>"
            "<session>"
            f"<session_id>{_VALID_SESSION_ID}</session_id>"
            "<title>Test Session</title>"
            "</session>"
        )
        receiver.process_message(ch, method, None, self._frontend_xml_bytes("session_created", body_xml))

        ch.basic_ack.assert_called_once_with(delivery_tag=42)
        ch.basic_nack.assert_not_called()

    @patch("receiver.get_odoo_connection")
    @patch("receiver.validate_xml")
    def test_session_updated_dispatched_and_acked(self, mock_validate, mock_odoo, ch, method):
        uid, models = 1, MagicMock()
        mock_odoo.return_value = (uid, models)
        models.execute_kw.return_value = []

        body_xml = (
            f"<identity_uuid>{_VALID_IDENTITY}</identity_uuid>"
            "<session>"
            f"<session_id>{_VALID_SESSION_ID}</session_id>"
            "<title>Updated</title>"
            "</session>"
        )
        receiver.process_message(ch, method, None, self._frontend_xml_bytes("session_updated", body_xml))

        ch.basic_ack.assert_called_once_with(delivery_tag=42)
        ch.basic_nack.assert_not_called()

    @patch("receiver.get_odoo_connection")
    @patch("receiver.validate_xml")
    def test_session_deleted_dispatched_and_acked(self, mock_validate, mock_odoo, ch, method):
        uid, models = 1, MagicMock()
        mock_odoo.return_value = (uid, models)
        models.execute_kw.return_value = []

        body_xml = (
            f"<identity_uuid>{_VALID_IDENTITY}</identity_uuid>"
            f"<session_id>{_VALID_SESSION_ID}</session_id>"
        )
        receiver.process_message(ch, method, None, self._frontend_xml_bytes("session_deleted", body_xml))

        ch.basic_ack.assert_called_once_with(delivery_tag=42)
        ch.basic_nack.assert_not_called()
