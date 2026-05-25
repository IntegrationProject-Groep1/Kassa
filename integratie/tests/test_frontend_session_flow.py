# test_frontend_session_flow.py
# Tests for the Frontend session architecture:
#   - XSD validation of session_created / session_updated / session_deleted
#   - process_session_created / process_session_updated / process_session_deleted handlers
#   - QR scan RPC routes to kassa.exchange (not planning.exchange)
#   - RabbitMQ binding verification for start_listening()
#
# Session messages describe the SESSION ITSELF (no user linked).
# Kassa only uses them to keep the POS product catalogue in sync.
# User ↔ session association happens exclusively via the QR scan RPC.
#
# Run with: pytest tests/test_frontend_session_flow.py -v

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

_VALID_MSG_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_VALID_SESSION_ID = "sess-0001"
_VALID_IDENTITY = "bbbbbbbb-cccc-dddd-eeee-ffffffffffff"


def _session_created_xml(
    message_id=_VALID_MSG_ID,
    session_id=_VALID_SESSION_ID,
    title="Workshop Python",
    price=None,
    start_datetime="2026-06-01T09:00:00",
    end_datetime="2026-06-01T11:00:00",
):
    price_el = f'<price currency="eur">{price}</price>' if price is not None else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<message>"
        "<header>"
        f"<message_id>{message_id}</message_id>"
        "<timestamp>2026-05-14T12:00:00</timestamp>"
        "<source>frontend</source>"
        "<type>session_created</type>"
        "<version>2.0</version>"
        "</header>"
        "<body>"
        f"<session_id>{session_id}</session_id>"
        f"<title>{title}</title>"
        f"<start_datetime>{start_datetime}</start_datetime>"
        f"<end_datetime>{end_datetime}</end_datetime>"
        f"{price_el}"
        "</body>"
        "</message>"
    )


def _session_updated_xml(
    message_id=_VALID_MSG_ID,
    session_id=_VALID_SESSION_ID,
    title="Workshop Python Updated",
    price=None,
    start_datetime="2026-06-01T09:00:00",
    end_datetime="2026-06-01T11:00:00",
):
    price_el = f'<price currency="eur">{price}</price>' if price is not None else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<message>"
        "<header>"
        f"<message_id>{message_id}</message_id>"
        "<timestamp>2026-05-14T12:00:00</timestamp>"
        "<source>frontend</source>"
        "<type>session_updated</type>"
        "<version>2.0</version>"
        "</header>"
        "<body>"
        f"<session_id>{session_id}</session_id>"
        f"<title>{title}</title>"
        f"<start_datetime>{start_datetime}</start_datetime>"
        f"<end_datetime>{end_datetime}</end_datetime>"
        f"{price_el}"
        "</body>"
        "</message>"
    )


def _session_deleted_xml(
    message_id=_VALID_MSG_ID,
    session_id=_VALID_SESSION_ID,
    reason=None,
    deleted_by=None,
):
    reason_el = f"<reason>{reason}</reason>" if reason else ""
    deleted_by_el = f"<deleted_by>{deleted_by}</deleted_by>" if deleted_by else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<message>"
        "<header>"
        f"<message_id>{message_id}</message_id>"
        "<timestamp>2026-05-14T12:00:00</timestamp>"
        "<source>frontend</source>"
        "<type>session_deleted</type>"
        "<version>2.0</version>"
        "</header>"
        "<body>"
        f"<session_id>{session_id}</session_id>"
        f"{reason_el}"
        f"{deleted_by_el}"
        "</body>"
        "</message>"
    )


def _root_from_xml(xml_str):
    return ET.fromstring(xml_str)


# ── XSD validation ─────────────────────────────────────────────────────────────

class TestSessionXsdValidation:

    # session_created
    def test_session_created_valid_without_price(self):
        receiver.validate_xml(_session_created_xml(), "session_created")

    def test_session_created_valid_with_price(self):
        receiver.validate_xml(_session_created_xml(price=25.0), "session_created")

    def test_session_created_invalid_missing_title(self):
        xml = _session_created_xml().replace("<title>Workshop Python</title>", "")
        with pytest.raises(ValueError, match="XSD validation failed"):
            receiver.validate_xml(xml, "session_created")

    def test_session_created_invalid_missing_session_id(self):
        xml = _session_created_xml().replace(f"<session_id>{_VALID_SESSION_ID}</session_id>", "")
        with pytest.raises(ValueError, match="XSD validation failed"):
            receiver.validate_xml(xml, "session_created")

    def test_session_created_wrong_source_rejected(self):
        xml = _session_created_xml().replace("<source>frontend</source>", "<source>planning</source>")
        with pytest.raises(ValueError, match="XSD validation failed"):
            receiver.validate_xml(xml, "session_created")

    def test_session_created_has_no_identity_uuid_in_body(self):
        # identity_uuid must NOT be a required field — session creation has no user
        xml = _session_created_xml()
        assert "<identity_uuid>" not in xml

    # session_updated
    def test_session_updated_valid_without_price(self):
        receiver.validate_xml(_session_updated_xml(), "session_updated")

    def test_session_updated_valid_with_price(self):
        receiver.validate_xml(_session_updated_xml(price=30.0), "session_updated")

    def test_session_updated_invalid_missing_session_id(self):
        xml = _session_updated_xml().replace(f"<session_id>{_VALID_SESSION_ID}</session_id>", "")
        with pytest.raises(ValueError, match="XSD validation failed"):
            receiver.validate_xml(xml, "session_updated")

    def test_session_updated_wrong_source_rejected(self):
        xml = _session_updated_xml().replace("<source>frontend</source>", "<source>crm</source>")
        with pytest.raises(ValueError, match="XSD validation failed"):
            receiver.validate_xml(xml, "session_updated")

    # session_deleted
    def test_session_deleted_valid_minimal(self):
        receiver.validate_xml(_session_deleted_xml(), "session_deleted")

    def test_session_deleted_valid_with_reason_and_deleted_by(self):
        receiver.validate_xml(_session_deleted_xml(reason="Cancelled", deleted_by="admin"), "session_deleted")

    def test_session_deleted_invalid_missing_session_id(self):
        xml = _session_deleted_xml().replace(f"<session_id>{_VALID_SESSION_ID}</session_id>", "")
        with pytest.raises(ValueError, match="XSD validation failed"):
            receiver.validate_xml(xml, "session_deleted")

    # user_sessions_response still accepts frontend source
    def test_user_sessions_response_accepts_frontend_source(self):
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<message>"
            "<header>"
            f"<message_id>{_VALID_MSG_ID}</message_id>"
            "<timestamp>2026-05-14T12:00:00</timestamp>"
            "<source>frontend</source>"
            "<type>user_sessions_response</type>"
            "<version>2.0</version>"
            f"<correlation_id>{_VALID_MSG_ID}</correlation_id>"
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
    """
    session_created only ensures the POS product exists.
    No partner lookup, no x_session_title update, no bus event.
    """

    def _root(self, **kwargs):
        return _root_from_xml(_session_created_xml(**kwargs))

    def test_ensures_pos_product_created(self, odoo):
        uid, models = odoo
        # product not found → category found → product created
        models.execute_kw.side_effect = [
            [],            # x_session_id search → not found
            [],            # name search → not found
            [{"id": 3}],  # pos.category search_read
            1,             # product.template create
        ]
        receiver.process_session_created(self._root(title="Workshop Python", session_id="s1"), uid, models)

        create_call = models.execute_kw.call_args_list[3]
        assert create_call[0][3] == "product.template"
        assert create_call[0][4] == "create"
        assert create_call[0][5][0]["name"] == "Workshop Python"

    def test_skips_create_when_product_already_exists(self, odoo):
        uid, models = odoo
        # found by x_session_id with all fields in sync → no write, no create
        models.execute_kw.side_effect = [
            [{"id": 7, "name": "Workshop Python", "list_price": 25.0, "x_session_id": "sess-0001"}],
        ]
        receiver.process_session_created(self._root(price=25.0), uid, models)

        all_calls = models.execute_kw.call_args_list
        creates = [c for c in all_calls if c[0][4] == "create"]
        assert len(creates) == 0

    def test_updates_product_price_when_different(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 7, "list_price": 10.0}],  # product exists with old price
            True,                              # product write new price
        ]
        receiver.process_session_created(self._root(price=25.0), uid, models)

        price_write = models.execute_kw.call_args_list[1]
        assert price_write[0][3] == "product.template"
        assert price_write[0][4] == "write"
        assert price_write[0][5][1]["list_price"] == 25.0

    def test_does_not_touch_any_partner(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [],         # product not found
            [{"id": 3}],
            1,
        ]
        receiver.process_session_created(self._root(), uid, models)

        all_calls = models.execute_kw.call_args_list
        partner_calls = [c for c in all_calls if c[0][3] == "res.partner"]
        assert len(partner_calls) == 0

    def test_raises_when_title_missing(self, odoo):
        uid, models = odoo
        xml = _session_created_xml().replace("<title>Workshop Python</title>", "<title></title>")
        root = _root_from_xml(xml)
        with pytest.raises(ValueError, match="session_created"):
            receiver.process_session_created(root, uid, models)

    def test_raises_when_session_id_missing(self, odoo):
        uid, models = odoo
        xml = _session_created_xml().replace(
            f"<session_id>{_VALID_SESSION_ID}</session_id>", "<session_id></session_id>"
        )
        root = _root_from_xml(xml)
        with pytest.raises(ValueError, match="session_created"):
            receiver.process_session_created(root, uid, models)


# ── process_session_updated ────────────────────────────────────────────────────

class TestProcessSessionUpdated:
    """
    session_updated only updates the POS product (title/price).
    No partner lookup, no x_session_title update, no bus event.
    """

    def _root(self, **kwargs):
        return _root_from_xml(_session_updated_xml(**kwargs))

    def test_updates_existing_product_price(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 7, "list_price": 10.0}],  # product found
            True,                              # product write
        ]
        receiver.process_session_updated(
            self._root(session_id="s1", title="Workshop Python Updated", price=20.0), uid, models
        )

        write_call = models.execute_kw.call_args_list[1]
        assert write_call[0][3] == "product.template"
        assert write_call[0][4] == "write"
        assert write_call[0][5][1]["list_price"] == 20.0

    def test_creates_product_when_not_found(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [],           # x_session_id search → not found
            [],           # name search → not found
            [{"id": 3}],  # category found
            1,            # product created
        ]
        receiver.process_session_updated(self._root(title="Brand New Session"), uid, models)

        create_call = models.execute_kw.call_args_list[3]
        assert create_call[0][3] == "product.template"
        assert create_call[0][4] == "create"

    def test_does_not_write_any_partner_when_none_registered(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 7, "list_price": 10.0}],  # product found by x_session_id
            True,                              # product write
            [],                                # partner search → no partners registered
        ]
        receiver.process_session_updated(self._root(price=15.0), uid, models)

        all_calls = models.execute_kw.call_args_list
        partner_writes = [c for c in all_calls if c[0][3] == "res.partner" and c[0][4] == "write"]
        assert len(partner_writes) == 0

    def test_raises_when_session_id_missing(self, odoo):
        uid, models = odoo
        xml = _session_updated_xml().replace(
            f"<session_id>{_VALID_SESSION_ID}</session_id>", "<session_id></session_id>"
        )
        root = _root_from_xml(xml)
        with pytest.raises(ValueError, match="session_updated"):
            receiver.process_session_updated(root, uid, models)


# ── process_session_deleted ────────────────────────────────────────────────────

class TestProcessSessionDeleted:
    """
    session_deleted only logs — no partner, no product changes.
    The POS product is kept because visitors may still pay for it via QR scan.
    """

    def _root(self, **kwargs):
        return _root_from_xml(_session_deleted_xml(**kwargs))

    def test_makes_no_odoo_calls(self, odoo):
        uid, models = odoo
        receiver.process_session_deleted(self._root(session_id="s1"), uid, models)
        models.execute_kw.assert_not_called()

    def test_does_not_delete_pos_product(self, odoo):
        uid, models = odoo
        receiver.process_session_deleted(self._root(session_id="s1"), uid, models)

        all_calls = models.execute_kw.call_args_list
        product_calls = [c for c in all_calls if c[0][3] == "product.template"]
        assert len(product_calls) == 0

    def test_handles_optional_reason(self, odoo):
        uid, models = odoo
        # Should not raise even with reason + deleted_by present
        receiver.process_session_deleted(
            self._root(session_id="s1", reason="Event cancelled", deleted_by="admin"),
            uid, models,
        )
        models.execute_kw.assert_not_called()

    def test_raises_when_session_id_missing(self, odoo):
        uid, models = odoo
        xml = _session_deleted_xml().replace(
            f"<session_id>{_VALID_SESSION_ID}</session_id>", "<session_id></session_id>"
        )
        root = _root_from_xml(xml)
        with pytest.raises(ValueError, match="session_deleted"):
            receiver.process_session_deleted(root, uid, models)


# ── QR scan routing ────────────────────────────────────────────────────────────

class TestQrScanRouting:
    """Verify _fetch_sessions_from_frontend sends to kassa.exchange, not planning.exchange."""

    def test_qr_scan_controller_uses_kassa_exchange_not_planning(self):
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
        assert "RABBIT_EXCHANGE" in source, \
            "Should use RABBIT_EXCHANGE env var for kassa.exchange"


# ── RabbitMQ binding verification ─────────────────────────────────────────────

class TestReceiverBindings:

    @patch("receiver.connect_to_rabbitmq")
    @patch("receiver.setup_exchange")
    @patch("receiver.flush_buffer")
    def test_binds_frontend_session_routing_keys(self, mock_flush, mock_setup, mock_connect):
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

        # Collect (exchange, routing_key) pairs from all queue_bind calls
        bindings = [
            (
                call_args[1].get("exchange") or (call_args[0][0] if call_args[0] else None),
                call_args[1].get("routing_key") or (call_args[0][2] if len(call_args[0]) > 2 else None),
            )
            for call_args in channel_mock.queue_bind.call_args_list
        ]

        expected = {
            ("frontend.exchange", "frontend.to.kassa.user_sessions_response"),
            ("frontend.exchange", "frontend.to.kassa.session.created"),
            ("frontend.exchange", "frontend.to.kassa.session.updated"),
            ("frontend.exchange", "frontend.to.kassa.session.deleted"),
        }
        for exchange, key in expected:
            assert (exchange, key) in bindings, \
                f"Missing binding: routing_key={key} on exchange={exchange}"

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


# ── process_message dispatch ───────────────────────────────────────────────────

class TestProcessMessageSessionTypes:
    """Verify process_message dispatches to the 3 session handlers correctly."""

    def _xml_bytes(self, msg_type, body_xml, message_id=_VALID_MSG_ID):
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<message>"
            "<header>"
            f"<message_id>{message_id}</message_id>"
            f"<type>{msg_type}</type>"
            "<source>frontend</source>"
            "<timestamp>2026-05-14T12:00:00</timestamp>"
            "<version>2.0</version>"
            "</header>"
            f"<body>{body_xml}</body>"
            "</message>"
        ).encode("utf-8")

    def _session_body(self, session_id=_VALID_SESSION_ID, title="Test Session"):
        return (
            f"<session_id>{session_id}</session_id>"
            f"<title>{title}</title>"
            "<start_datetime>2026-06-01T09:00:00</start_datetime>"
            "<end_datetime>2026-06-01T11:00:00</end_datetime>"
        )

    @patch("receiver.get_odoo_connection")
    @patch("receiver.validate_xml")
    def test_session_created_dispatched_and_acked(self, mock_validate, mock_odoo, ch, method):
        uid, models = 1, MagicMock()
        mock_odoo.return_value = (uid, models)
        models.execute_kw.side_effect = [[], [{"id": 3}], 1]

        receiver.process_message(
            ch, method, None,
            self._xml_bytes("session_created", self._session_body()),
        )

        ch.basic_ack.assert_called_once_with(delivery_tag=42)
        ch.basic_nack.assert_not_called()

    @patch("receiver.get_odoo_connection")
    @patch("receiver.validate_xml")
    def test_session_updated_dispatched_and_acked(self, mock_validate, mock_odoo, ch, method):
        uid, models = 1, MagicMock()
        mock_odoo.return_value = (uid, models)
        models.execute_kw.side_effect = [[], [{"id": 3}], 1]

        receiver.process_message(
            ch, method, None,
            self._xml_bytes("session_updated", self._session_body(title="Updated")),
        )

        ch.basic_ack.assert_called_once_with(delivery_tag=42)
        ch.basic_nack.assert_not_called()

    @patch("receiver.get_odoo_connection")
    @patch("receiver.validate_xml")
    def test_session_deleted_dispatched_and_acked(self, mock_validate, mock_odoo, ch, method):
        uid, models = 1, MagicMock()
        mock_odoo.return_value = (uid, models)

        receiver.process_message(
            ch, method, None,
            self._xml_bytes("session_deleted", f"<session_id>{_VALID_SESSION_ID}</session_id>"),
        )

        ch.basic_ack.assert_called_once_with(delivery_tag=42)
        ch.basic_nack.assert_not_called()
        models.execute_kw.assert_not_called()
