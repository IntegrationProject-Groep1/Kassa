# test_receiver.py – Unit tests for receiver.py
# Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026
#
# Run with:  pytest tests/test_receiver.py -v
#
# All Odoo XML-RPC calls and RabbitMQ interactions are mocked.
# No live services are required.

import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import pytest

import receiver


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_idempotency_cache():
    """Reset the in-memory LRU cache before and after each test."""
    receiver.seen_message_ids.clear()
    yield
    receiver.seen_message_ids.clear()


@pytest.fixture
def odoo():
    """Return (uid, models_mock) mimicking get_odoo_connection()."""
    uid = 1
    models = MagicMock()
    return uid, models


@pytest.fixture
def ch():
    """Mock RabbitMQ channel."""
    return MagicMock()


@pytest.fixture
def method():
    """Mock RabbitMQ method with a delivery tag."""
    m = MagicMock()
    m.delivery_tag = 42
    return m


# ── Helpers ────────────────────────────────────────────────────────────────────

def _xml_bytes(msg_type: str, body_xml: str, message_id: str = "test-msg-001") -> bytes:
    """Build a minimal valid message XML for tests."""
    source = "iot_gateway" if msg_type == "badge_scanned" else "crm"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<message>"
        "<header>"
        f"<message_id>{message_id}</message_id>"
        f"<type>{msg_type}</type>"
        f"<source>{source}</source>"
        "<timestamp>2026-03-28T12:00:00Z</timestamp>"
        "<version>2.0</version>"
        "</header>"
        f"<body>{body_xml}</body>"
        "</message>"
    ).encode("utf-8")


# ── is_duplicate ───────────────────────────────────────────────────────────────

class TestIsDuplicate:
    def test_first_seen_returns_false(self):
        assert receiver.is_duplicate("msg-abc") is False

    def test_second_seen_returns_true(self):
        receiver.is_duplicate("msg-abc")
        assert receiver.is_duplicate("msg-abc") is True

    def test_different_ids_not_duplicate(self):
        assert receiver.is_duplicate("msg-001") is False
        assert receiver.is_duplicate("msg-002") is False

    def test_lru_eviction(self):
        # Fill cache to MAX_CACHE_SIZE + 1; first entry should be evicted
        original_max = receiver.MAX_CACHE_SIZE
        receiver.MAX_CACHE_SIZE = 3
        try:
            receiver.is_duplicate("a")
            receiver.is_duplicate("b")
            receiver.is_duplicate("c")
            receiver.is_duplicate("d")  # triggers eviction of "a"
            # "a" was evicted → no longer a duplicate
            assert receiver.is_duplicate("a") is False
            # re-adding "a" evicts "b" as well; "c" and "d" survive
            assert receiver.is_duplicate("c") is True
            assert receiver.is_duplicate("d") is True
        finally:
            receiver.MAX_CACHE_SIZE = original_max


# ── validate_xml ───────────────────────────────────────────────────────────────

class TestValidateXml:
    def test_unknown_type_skips_validation(self):
        # Should not raise – schema is simply absent
        receiver.validate_xml("<message/>", "totally_unknown_type")

    def test_missing_schema_file_skips_validation(self, tmp_path, monkeypatch):
        # Point SCHEMA_MAP to a non-existent file
        monkeypatch.setitem(receiver.SCHEMA_MAP, "badge_scanned", str(tmp_path / "missing.xsd"))
        receiver.validate_xml("<message/>", "badge_scanned")  # should not raise

    def test_valid_badge_scanned_xml_passes(self):
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<message>"
            "<header>"
            "<message_id>550e8400-e29b-41d4-a716-446655440000</message_id>"
            "<timestamp>2026-03-28T12:00:00Z</timestamp>"
            "<source>kassa</source>"
            "<type>badge_scanned</type>"
            "<version>2.0</version>"
            "</header>"
            "<body><badge_id>BADGE-001</badge_id>"
            "<location>bar</location>"
            "<scanned_at>2026-03-28T12:00:00Z</scanned_at></body>"
            "</message>"
        )
        receiver.validate_xml(xml, "badge_scanned")  # should not raise

    def test_valid_user_event_passes(self):
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<user_event>"
            "<event>UserCreated</event>"
            "<master_uuid>a1b2c3d4-e5f6-7890-abcd-ef1234567890</master_uuid>"
            "<email>jan.peeters@ehb.be</email>"
            "<source_system>frontend</source_system>"
            "<timestamp>2026-05-08T10:00:00</timestamp>"
            "</user_event>"
        )
        receiver.validate_xml(xml, "user_event")  # should not raise

    def test_invalid_user_event_raises(self):
        # Missing required fields — should fail XSD validation
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<user_event>"
            "<event>UserCreated</event>"
            "</user_event>"
        )
        with pytest.raises(ValueError, match="XSD validation failed"):
            receiver.validate_xml(xml, "user_event")


# ── process_new_registration ───────────────────────────────────────────────────

class TestProcessNewRegistration:
    NEW_REG_BODY = (
        "<customer>"
        "<identity_uuid>550e8400-e29b-41d4-a716-446655440001</identity_uuid>"
        "<email>test@example.com</email>"
        "<date_of_birth>1996-01-01</date_of_birth>"
        "<contact><first_name>Alice</first_name><last_name>Wonderland</last_name></contact>"
        "<type>private</type>"
        "<session_id>sess-001</session_id>"
        "<payment_due><amount currency=\"eur\">25.00</amount><status>unpaid</status></payment_due>"
        "</customer>"
    )

    def _root(self):
        return ET.fromstring(
            "<message><header/><body>" + self.NEW_REG_BODY + "</body></message>"
        )

    def test_creates_new_partner_when_not_found(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [],   # search_read → no existing partner
            99,   # create → new partner id
        ]
        receiver.process_new_registration(self._root(), uid, models)

        create_call = models.execute_kw.call_args_list[1]
        assert create_call[0][4] == "create"
        vals = create_call[0][5][0]
        assert vals["x_user_id"] == "550e8400-e29b-41d4-a716-446655440001"
        assert vals["name"] == "Alice Wonderland"
        assert vals["is_company"] is False

    def test_updates_existing_partner(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 5, "name": "Alice", "x_user_id": "550e8400-e29b-41d4-a716-446655440001"}],  # search_read
            True,                                                    # write
        ]
        receiver.process_new_registration(self._root(), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        assert write_call[0][4] == "write"
        assert write_call[0][5][0] == [5]

    def test_raises_when_identity_uuid_missing(self, odoo):
        uid, models = odoo
        root = ET.fromstring(
            "<message><header/><body>"
            "<customer>"
            "<email>a@b.com</email><contact><first_name>X</first_name>"
            "<last_name>Y</last_name></contact><type>private</type>"
            "<payment_due><amount currency=\"eur\">0</amount><status>unpaid</status></payment_due>"
            "</customer>"
            "</body></message>"
        )
        with pytest.raises(ValueError, match="identity_uuid missing"):
            receiver.process_new_registration(root, uid, models)

    def test_company_sets_is_company_true(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[], 10]
        root = ET.fromstring(
            "<message><header/><body>"
            "<customer>"
            "<identity_uuid>550e8400-e29b-41d4-a716-446655440002</identity_uuid>"
            "<email>info@corp.be</email><contact><first_name>Corp</first_name><last_name>Member</last_name></contact>"
            "<company_name>Corp NV</company_name><date_of_birth>1990-01-01</date_of_birth>"
            "<type>company</type><vat_number>BE0123</vat_number>"
            "<session_id>s1</session_id>"
            "<payment_due><amount currency=\"eur\">100</amount><status>paid</status></payment_due>"
            "</customer>"
            "</body></message>"
        )
        receiver.process_new_registration(root, uid, models)
        create_call = models.execute_kw.call_args_list[1]
        vals = create_call[0][5][0]
        assert vals["is_company"] is True
        assert vals["vat"] == "BE0123"


# ── _ensure_session_product ────────────────────────────────────────────────────

class TestEnsureSessionProduct:
    def test_creates_product_when_not_found(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [],          # search_read product.template → not found
            [{"id": 10}],  # search_read pos.category "Sessions"
            42,          # create product.template → new id
        ]
        receiver._ensure_session_product(uid, models, "Workshop: IoT met Python")

        create_call = models.execute_kw.call_args_list[2]
        assert create_call[0][3] == "product.template"
        assert create_call[0][4] == "create"
        vals = create_call[0][5][0]
        assert vals["name"] == "Workshop: IoT met Python"
        assert vals["available_in_pos"] is True
        assert vals["type"] == "consu"
        assert vals["list_price"] == 0.0

    def test_skips_when_product_already_exists(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 7}],  # search_read product.template → found
        ]
        receiver._ensure_session_product(uid, models, "Workshop: IoT met Python")

        # Only one XML-RPC call (the search); no create
        assert models.execute_kw.call_count == 1

    def test_new_registration_with_session_title_calls_ensure_product(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [],              # search_read res.partner → not found
            99,              # create partner
            [],              # search_read product.template → not found
            [{"id": 10}],   # search_read pos.category
            55,              # create product
            True,            # pos.order.send_partner_bus_event
        ]
        root = ET.fromstring(
            "<message><header/><body>"
            "<customer>"
            "<identity_uuid>550e8400-e29b-41d4-a716-446655440099</identity_uuid>"
            "<email>t@t.com</email>"
            "<contact><first_name>Jan</first_name><last_name>Jansen</last_name></contact>"
            "<type>private</type>"
            "<session_title>Workshop: IoT met Python</session_title>"
            "<payment_due><amount currency=\"eur\">25.00</amount><status>unpaid</status></payment_due>"
            "</customer>"
            "</body></message>"
        )
        receiver.process_new_registration(root, uid, models)

        # Verify product creation was called with the correct session title
        product_create = next(
            c for c in models.execute_kw.call_args_list
            if c[0][3] == "product.template" and c[0][4] == "create"
        )
        assert product_create[0][5][0]["name"] == "Workshop: IoT met Python"

    def test_new_registration_without_session_title_skips_product(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [],   # search_read res.partner → not found
            99,   # create partner
            True, # bus event
        ]
        root = ET.fromstring(
            "<message><header/><body>"
            "<customer>"
            "<identity_uuid>550e8400-e29b-41d4-a716-446655440099</identity_uuid>"
            "<email>t@t.com</email>"
            "<contact><first_name>Jan</first_name><last_name>Jansen</last_name></contact>"
            "<type>private</type>"
            "<payment_due><amount currency=\"eur\">25.00</amount><status>unpaid</status></payment_due>"
            "</customer>"
            "</body></message>"
        )
        receiver.process_new_registration(root, uid, models)

        # No product.template calls
        product_calls = [
            c for c in models.execute_kw.call_args_list
            if c[0][3] == "product.template"
        ]
        assert product_calls == []


# ── process_profile_update ─────────────────────────────────────────────────────

class TestProcessProfileUpdate:
    BODY = (
        "<identity_uuid>550e8400-e29b-41d4-a716-446655440003</identity_uuid>"
        "<email>new@example.com</email>"
        "<contact><first_name>Bob</first_name><last_name>Builder</last_name></contact>"
        "<date_of_birth>1986-01-01</date_of_birth>"
        "<type>private</type>"
    )

    def _root(self):
        return ET.fromstring("<message><header/><body>" + self.BODY + "</body></message>")

    def test_updates_existing_partner(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 7, "name": "Bob Old"}],
            True,
        ]
        receiver.process_profile_update(self._root(), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        assert write_call[0][4] == "write"
        vals = write_call[0][5][1]
        assert vals["email"] == "new@example.com"
        assert vals["x_date_of_birth"] == "1986-01-01"

    def test_creates_partner_when_not_found(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[], 8]
        receiver.process_profile_update(self._root(), uid, models)

        create_call = models.execute_kw.call_args_list[1]
        assert create_call[0][4] == "create"
        vals = create_call[0][5][0]
        assert vals["x_user_id"] == "550e8400-e29b-41d4-a716-446655440003"

    def test_updates_payment_info(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[{"id": 7}], True]
        xml = (
            "<message><header/><body>"
            "<identity_uuid>550e8400-e29b-41d4-a716-446655440003</identity_uuid>"
            "<email>x@x.com</email>"
            "<contact><first_name>X</first_name><last_name>Y</last_name></contact>"
            "<payment_due><amount>50.0</amount><status>paid</status></payment_due>"
            "</body></message>"
        )
        receiver.process_profile_update(ET.fromstring(xml), uid, models)
        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        assert vals["x_payment_status"] == "paid"
        assert vals["x_outstanding_amount"] == 50.0


# ── process_badge_scan ─────────────────────────────────────────────────────────

class TestProcessBadgeScan:
    def _root(self, badge_id: str):
        return ET.fromstring(
            "<message>"
            "<header><message_id>550e8400-e29b-41d4-a716-446655440004</message_id></header>"
            "<body>"
            f"<badge_id>{badge_id}</badge_id>"
            "<location>session</location>"
            "<scanned_at>2026-04-20T10:00:00Z</scanned_at>"
            "</body>"
            "</message>"
        )

    def test_known_badge_prints_info(self, odoo, caplog):
        import logging
        caplog.set_level(logging.INFO)
        uid, models = odoo
        models.execute_kw.return_value = [
            {"id": 3, "name": "Alice", "x_user_id": "550e8400-e29b-41d4-a716-446655440001",
             "x_wallet_balance": 12.50, "x_date_of_birth": "1996-01-01", "is_company": False}
        ]
        receiver.process_badge_scan(self._root("BADGE-001"), uid, models)

        assert "Processing badge(BADGE-001) scan from session at 2026-04-20T10:00:00Z" in caplog.text
        assert "Recognised: Odoo ID=3" in caplog.text
        assert "Location=session" in caplog.text

    @patch("receiver.send_error_to_queue")
    def test_unknown_badge_sends_error(self, mock_send_error, odoo):
        uid, models = odoo
        models.execute_kw.return_value = []
        receiver.process_badge_scan(self._root("BADGE-UNKNOWN"), uid, models)
        mock_send_error.assert_called_once_with(
            error_code="badge_not_found",
            related_message_id="550e8400-e29b-41d4-a716-446655440004",
            error_description="Badge BADGE-UNKNOWN not found in local Odoo cache.",
        )

    def test_missing_identifier_raises(self, odoo):
        uid, models = odoo
        root = ET.fromstring(
            "<message><header/><body><location>bar</location></body></message>"
        )
        with pytest.raises(ValueError, match="neither badge_id nor identity_uuid"):
            receiver.process_badge_scan(root, uid, models)


# ── process_cancel_registration ───────────────────────────────────────────────

class TestProcessCancelRegistration:
    def _root(self, identity_uuid: str = "550e8400-e29b-41d4-a716-446655440005"):
        return ET.fromstring(
            "<message><header/><body>"
            f"<identity_uuid>{identity_uuid}</identity_uuid>"
            "<session_id>sess-001</session_id>"
            "</body></message>"
        )

    def test_deactivates_existing_partner(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 9, "name": "Carol"}],
            True,
        ]
        receiver.process_cancel_registration(self._root(), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        assert write_call[0][4] == "write"
        assert write_call[0][5][1] == {"active": False}

    def test_no_action_when_not_found(self, odoo, caplog):
        uid, models = odoo
        models.execute_kw.return_value = []
        receiver.process_cancel_registration(self._root(), uid, models)
        # write should NOT have been called
        for c in models.execute_kw.call_args_list:
            assert c[0][4] != "write"
        assert "no action" in caplog.text

    def test_raises_when_identity_uuid_missing(self, odoo):
        uid, models = odoo
        root = ET.fromstring(
            "<message><header/><body><session_id>s</session_id></body></message>"
        )
        with pytest.raises(ValueError, match="identity_uuid missing"):
            receiver.process_cancel_registration(root, uid, models)


# ── process_message (full pipeline) ───────────────────────────────────────────

class TestProcessMessage:
    """End-to-end tests for the process_message RabbitMQ callback."""

    @patch("receiver.get_odoo_connection")
    @patch("receiver.validate_xml")
    def test_acks_on_success(self, mock_validate, mock_odoo, ch, method):
        uid = 1
        models = MagicMock()
        models.execute_kw.side_effect = [[], 50]  # create new partner
        mock_odoo.return_value = (uid, models)

        body = _xml_bytes(
            "new_registration",
            "<customer>"
            "<identity_uuid>550e8400-e29b-41d4-a716-446655440001</identity_uuid>"
            "<email>x@x.com</email><contact><first_name>X</first_name>"
            "<last_name>Y</last_name></contact><type>private</type>"
            "<date_of_birth>2006-01-01</date_of_birth><session_id>s1</session_id>"
            "<payment_due><amount currency=\"eur\">10</amount><status>unpaid</status></payment_due>"
            "</customer>",
        )
        receiver.process_message(ch, method, None, body)
        ch.basic_ack.assert_called_once_with(delivery_tag=42)
        ch.basic_nack.assert_not_called()

    @patch("receiver.get_odoo_connection")
    @patch("receiver.validate_xml")
    def test_successful_delivery_marks_message_id(self, mock_validate, mock_odoo, ch, method):
        uid = 1
        models = MagicMock()
        models.execute_kw.side_effect = [[], 50]
        mock_odoo.return_value = (uid, models)

        body = _xml_bytes(
            "new_registration",
            "<customer>"
            "<identity_uuid>550e8400-e29b-41d4-a716-446655440001</identity_uuid>"
            "<email>x@x.com</email><contact><first_name>X</first_name>"
            "<last_name>Y</last_name></contact><type>private</type>"
            "<date_of_birth>2006-01-01</date_of_birth><session_id>s1</session_id>"
            "<payment_due><amount currency=\"eur\">10</amount><status>unpaid</status></payment_due>"
            "</customer>",
            message_id="550e8400-e29b-41d4-a716-446655440006",
        )

        receiver.process_message(ch, method, None, body)

        assert "550e8400-e29b-41d4-a716-446655440006" in receiver.seen_message_ids

    @patch("receiver.send_error_to_queue")
    def test_nacks_on_invalid_xml(self, mock_send_error, ch, method):
        receiver.process_message(ch, method, None, b"not valid xml <<<")
        ch.basic_nack.assert_called_once_with(delivery_tag=42, requeue=False)
        mock_send_error.assert_called_once()
        assert mock_send_error.call_args[0][0] == "invalid_xml_format"

    @patch("receiver.send_error_to_queue")
    def test_nacks_on_unknown_message_type(self, mock_send_error, ch, method):
        body = _xml_bytes("completely_unknown", "<data/>")
        receiver.process_message(ch, method, None, body)
        ch.basic_nack.assert_called_once_with(delivery_tag=42, requeue=False)
        mock_send_error.assert_called()

    def test_acks_duplicate_without_processing(self, ch, method):
        receiver.seen_message_ids["550e8400-e29b-41d4-a716-446655440001"] = "2026-01-01T00:00:00Z"

        body = _xml_bytes("new_registration", "<customer/>", message_id="550e8400-e29b-41d4-a716-446655440001")
        receiver.process_message(ch, method, None, body)

        ch.basic_ack.assert_called_once_with(delivery_tag=42)
        ch.basic_nack.assert_not_called()

    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    @patch("receiver.validate_xml")
    def test_nacks_on_odoo_connection_error(self, mock_validate, mock_odoo, mock_send_error, ch, method):
        mock_odoo.side_effect = ConnectionError("Odoo down")
        body = _xml_bytes("badge_scanned", "<badge_id>B1</badge_id><location>bar</location>")
        receiver.process_message(ch, method, None, body)

        # In the new robust receiver, we basic_publish to retry queue and basic_ack the original
        ch.basic_publish.assert_called_once()
        routing_key = ch.basic_publish.call_args[1]["routing_key"]
        assert "retry" in routing_key
        ch.basic_ack.assert_called_once_with(delivery_tag=42)
        ch.basic_nack.assert_not_called()

    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    @patch("receiver.validate_xml")
    def test_odoo_failure_does_not_cache_message_id(self, mock_validate, mock_odoo, mock_send_error, ch, method):
        mock_odoo.side_effect = ConnectionError("Temporary Odoo outage")
        body = _xml_bytes(
            "badge_scanned",
            "<badge_id>B1</badge_id><location>bar</location>",
            message_id="550e8400-e29b-41d4-a716-446655440007",
        )

        receiver.process_message(ch, method, None, body)

        # Should NOT be in seen_message_ids yet (only after successful Odoo write)
        assert "550e8400-e29b-41d4-a716-446655440007" not in receiver.seen_message_ids
        ch.basic_ack.assert_called_once()

    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    @patch("receiver.validate_xml")
    def test_nacks_on_missing_type_field(self, mock_validate, mock_odoo, mock_send_error, ch, method):
        body = (
            b'<?xml version="1.0"?>'
            b"<message>"
            b"<header><message_id>550e8400-e29b-41d4-a716-446655440008</message_id></header>"
            b"<body/>"
            b"</message>"
        )
        receiver.process_message(ch, method, None, body)
        ch.basic_nack.assert_called_once_with(delivery_tag=42, requeue=False)

    @patch("receiver.get_odoo_connection")
    @patch("receiver.validate_xml")
    def test_cancel_registration_acks_on_success(self, mock_validate, mock_odoo, ch, method):
        uid = 1
        models = MagicMock()
        models.execute_kw.side_effect = [[{"id": 3, "name": "Dave"}], True]
        mock_odoo.return_value = (uid, models)

        body = _xml_bytes(
            "cancel_registration",
            "<identity_uuid>550e8400-e29b-41d4-a716-446655440009</identity_uuid><session_id>s1</session_id>",
        )
        receiver.process_message(ch, method, None, body)
        ch.basic_ack.assert_called_once_with(delivery_tag=42)

    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    @patch("receiver.validate_xml")
    def test_badge_scan_unknown_still_acks(self, mock_validate, mock_odoo, mock_send_error, ch, method):
        """Unknown badge → sends error but must still ACK (not NACK)."""
        uid = 1
        models = MagicMock()
        models.execute_kw.return_value = []  # badge not found
        mock_odoo.return_value = (uid, models)

        body = _xml_bytes("badge_scanned", "<badge_id>BADGE-X</badge_id><location>bar</location>")
        receiver.process_message(ch, method, None, body)

        ch.basic_ack.assert_called_once_with(delivery_tag=42)
        ch.basic_nack.assert_not_called()
        expected_msg = "Badge BADGE-X not found in local Odoo cache."
        mock_send_error.assert_called_once_with(
            error_code="badge_not_found",
            related_message_id="test-msg-001",
            error_description=expected_msg,
        )


# ── _publish_partner_bus_event ─────────────────────────────────────────────────

class TestPublishPartnerBusEvent:
    def test_calls_pos_order_send_partner_bus_event(self, odoo):
        uid, models = odoo
        models.execute_kw.return_value = True
        receiver._publish_partner_bus_event(uid, models, 42, 25.0, "unpaid", "Alice")

        call = models.execute_kw.call_args
        assert call[0][3] == "pos.order"
        assert call[0][4] == "send_partner_bus_event"
        args = call[0][5]
        assert args[0] == 42          # partner_id
        assert args[1] == 25.0        # outstanding_amount
        assert args[2] == "unpaid"    # payment_status
        assert args[3] == "Alice"     # name

    def test_does_not_raise_on_error(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = Exception("bus down")
        # Must not raise — best-effort publish
        receiver._publish_partner_bus_event(uid, models, 1, 0.0, "paid", "Bob")


# ── process_new_registration — payment fields ──────────────────────────────────

class TestProcessNewRegistrationPaymentFields:
    NEW_REG_BODY = (
        "<customer>"
        "<identity_uuid>550e8400-e29b-41d4-a716-446655440001</identity_uuid>"
        "<email>test@example.com</email>"
        "<date_of_birth>1996-01-01</date_of_birth>"
        "<contact><first_name>Alice</first_name><last_name>Wonderland</last_name></contact>"
        "<type>private</type>"
        "<session_id>sess-001</session_id>"
        "<payment_due><amount currency=\"eur\">25.00</amount><status>unpaid</status></payment_due>"
        "</customer>"
    )

    def _root(self):
        return ET.fromstring(
            "<message><header/><body>" + self.NEW_REG_BODY + "</body></message>"
        )

    def test_payment_fields_included_in_create(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[], 99, True]  # search, create, bus sendone
        receiver.process_new_registration(self._root(), uid, models)

        create_call = models.execute_kw.call_args_list[1]
        vals = create_call[0][5][0]
        assert vals["x_outstanding_amount"] == 25.0
        assert vals["x_payment_status"] == "unpaid"

    def test_payment_fields_included_in_update(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 5, "name": "Alice Wonderland", "x_user_id": "550e8400-e29b-41d4-a716-446655440001"}],
            True, True,  # write, bus sendone
        ]
        receiver.process_new_registration(self._root(), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        assert vals["x_outstanding_amount"] == 25.0
        assert vals["x_payment_status"] == "unpaid"

    def test_bus_event_published_after_create(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[], 99, True]
        receiver.process_new_registration(self._root(), uid, models)

        bus_call = models.execute_kw.call_args_list[2]
        assert bus_call[0][3] == "pos.order"
        assert bus_call[0][4] == "send_partner_bus_event"

    def test_zero_amount_on_invalid_float(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[], 99, True]
        root = ET.fromstring(
            "<message><header/><body>"
            "<customer><identity_uuid>550e8400-e29b-41d4-a716-446655440001</identity_uuid>"
            "<email>a@b.com</email><contact><first_name>X</first_name>"
            "<last_name>Y</last_name></contact><type>private</type>"
            "<date_of_birth>2000-01-01</date_of_birth><session_id>s1</session_id>"
            "<payment_due><amount currency=\"eur\">not-a-number</amount><status>unpaid</status></payment_due>"
            "</customer>"
            "</body></message>"
        )
        receiver.process_new_registration(root, uid, models)
        create_call = models.execute_kw.call_args_list[1]
        vals = create_call[0][5][0]
        assert vals["x_outstanding_amount"] == 0.0


# ── process_profile_update — payment_due handling ─────────────────────────────

class TestProcessProfileUpdatePaymentDue:
    BASE_BODY = (
        "<identity_uuid>550e8400-e29b-41d4-a716-446655440003</identity_uuid>"
        "<email>new@example.com</email>"
        "<contact><first_name>Bob</first_name><last_name>Builder</last_name></contact>"
        "<type>private</type>"
    )

    def _root(self, extra: str = ""):
        return ET.fromstring(
            "<message><header/><body>" + self.BASE_BODY + extra + "</body></message>"
        )

    def test_payment_fields_written_when_payment_due_present(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 7, "name": "Bob Old"}],
            True, True,  # write, bus sendone
        ]
        root = self._root("<payment_due><amount>50.00</amount><status>unpaid</status></payment_due>")
        receiver.process_profile_update(root, uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        assert vals["x_outstanding_amount"] == 50.0
        assert vals["x_payment_status"] == "unpaid"

    def test_payment_fields_absent_when_no_payment_due(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 7, "name": "Bob Old"}],
            True,  # write only — no bus call expected
        ]
        receiver.process_profile_update(self._root(), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        assert "x_outstanding_amount" not in vals
        assert "x_payment_status" not in vals

    def test_bus_event_published_when_payment_due_present(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 7, "name": "Bob Builder"}],
            True, True,
        ]
        root = self._root("<payment_due><amount>10.00</amount><status>paid</status></payment_due>")
        receiver.process_profile_update(root, uid, models)

        bus_call = models.execute_kw.call_args_list[2]
        assert bus_call[0][3] == "pos.order"
        assert bus_call[0][4] == "send_partner_bus_event"
        args = bus_call[0][5]
        assert args[2] == "paid"  # payment_status is the 3rd positional arg

    def test_no_bus_event_without_payment_due(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 7, "name": "Bob Builder"}],
            True,
        ]
        receiver.process_profile_update(self._root(), uid, models)

        all_models_calls = [c[0][3] for c in models.execute_kw.call_args_list]
        assert "bus.bus" not in all_models_calls
