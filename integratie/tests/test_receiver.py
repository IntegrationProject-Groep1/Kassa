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
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<message>"
        "<header>"
        f"<message_id>{message_id}</message_id>"
        f"<type>{msg_type}</type>"
        "<source>test</source>"
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
            "<message_id>x</message_id>"
            "<type>badge_scanned</type>"
            "<source>s</source>"
            "<timestamp>2026-03-28T12:00:00Z</timestamp>"
            "<version>2.0</version>"
            "</header>"
            "<body><badge_id>BADGE-001</badge_id><location>bar</location></body>"
            "</message>"
        )
        receiver.validate_xml(xml, "badge_scanned")  # should not raise

    def test_invalid_xml_raises_value_error(self):
        # badge_scanned body missing required badge_id
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<message>"
            "<header>"
            "<message_id>x</message_id>"
            "<type>badge_scanned</type>"
            "<source>s</source>"
            "<timestamp>2026-03-28T12:00:00Z</timestamp>"
            "<version>2.0</version>"
            "</header>"
            "<body><location>bar</location></body>"
            "</message>"
        )
        with pytest.raises(ValueError, match="XSD validation failed"):
            receiver.validate_xml(xml, "badge_scanned")


# ── process_new_registration ───────────────────────────────────────────────────

class TestProcessNewRegistration:
    NEW_REG_BODY = (
        "<customer>"
        "<email>test@example.com</email>"
        "<name>Alice</name>"
        "<type>private</type>"
        "<user_id>uid-001</user_id>"
        "<date_of_birth>1996-01-01</date_of_birth>"
        "</customer>"
        "<payment_due><amount>25.00</amount><status>unpaid</status></payment_due>"
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
        assert vals["x_user_id"] == "uid-001"
        assert vals["name"] == "Alice"
        assert vals["is_company"] is False

    def test_updates_existing_partner(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 5, "name": "Alice", "x_user_id": "uid-001"}],  # search_read
            True,                                                    # write
        ]
        receiver.process_new_registration(self._root(), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        assert write_call[0][4] == "write"
        assert write_call[0][5][0] == [5]

    def test_raises_when_user_id_missing(self, odoo):
        uid, models = odoo
        root = ET.fromstring(
            "<message><header/><body>"
            "<customer><email>a@b.com</email><name>X</name><type>private</type></customer>"
            "<payment_due><amount>0</amount><status>unpaid</status></payment_due>"
            "</body></message>"
        )
        with pytest.raises(ValueError, match="user_id missing"):
            receiver.process_new_registration(root, uid, models)

    def test_company_sets_is_company_true(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[], 10]
        root = ET.fromstring(
            "<message><header/><body>"
            "<customer>"
            "<email>info@corp.be</email><name>Corp</name><company_name>Corp NV</company_name>"
            "<type>company</type><vat_number>BE0123</vat_number><user_id>uid-002</user_id>"
            "</customer>"
            "<payment_due><amount>100</amount><status>paid</status></payment_due>"
            "</body></message>"
        )
        receiver.process_new_registration(root, uid, models)
        create_call = models.execute_kw.call_args_list[1]
        vals = create_call[0][5][0]
        assert vals["is_company"] is True
        assert vals["vat"] == "BE0123"


# ── process_profile_update ─────────────────────────────────────────────────────

class TestProcessProfileUpdate:
    BODY = (
        "<user_id>uid-003</user_id>"
        "<email>new@example.com</email>"
        "<name>Bob</name>"
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
        assert vals["x_user_id"] == "uid-003"

    def test_raises_when_user_id_missing(self, odoo):
        uid, models = odoo
        root = ET.fromstring(
            "<message><header/><body><email>a@b.com</email></body></message>"
        )
        with pytest.raises(ValueError, match="user_id missing"):
            receiver.process_profile_update(root, uid, models)


# ── process_badge_scan ─────────────────────────────────────────────────────────

class TestProcessBadgeScan:
    def _root(self, badge_id: str):
        return ET.fromstring(
            "<message>"
            "<header><message_id>scan-001</message_id></header>"
            "<body>"
            f"<badge_id>{badge_id}</badge_id>"
            "<location>bar</location>"
            "</body>"
            "</message>"
        )

    def test_known_badge_prints_info(self, odoo, caplog):
        import logging
        caplog.set_level(logging.INFO)
        uid, models = odoo
        models.execute_kw.return_value = [
            {"id": 3, "name": "Alice", "x_user_id": "uid-001",
             "x_wallet_balance": 12.50, "x_date_of_birth": "1996-01-01", "is_company": False}
        ]
        receiver.process_badge_scan(self._root("BADGE-001"), uid, models)

        assert "Badge recognised: Odoo ID=3" in caplog.text
        assert "Location=bar" in caplog.text
        assert "BADGE-001" not in caplog.text  # PII removed
        assert "Alice" not in caplog.text      # PII removed

    @patch("receiver.send_error_to_queue")
    def test_unknown_badge_sends_error(self, mock_send_error, odoo):
        uid, models = odoo
        models.execute_kw.return_value = []
        receiver.process_badge_scan(self._root("BADGE-UNKNOWN"), uid, models)
        mock_send_error.assert_called_once_with(
            error_code="badge_not_found",
            related_message_id="scan-001",
            error_description="Badge BADGE-UNKNOWN not found in local Odoo cache.",
        )

    def test_missing_badge_id_raises(self, odoo):
        uid, models = odoo
        root = ET.fromstring(
            "<message><header/><body><location>bar</location></body></message>"
        )
        with pytest.raises(ValueError, match="badge_id missing"):
            receiver.process_badge_scan(root, uid, models)


# ── process_cancel_registration ───────────────────────────────────────────────

class TestProcessCancelRegistration:
    def _root(self, user_id: str = "uid-004"):
        return ET.fromstring(
            "<message><header/><body>"
            f"<user_id>{user_id}</user_id>"
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

    def test_raises_when_user_id_missing(self, odoo):
        uid, models = odoo
        root = ET.fromstring(
            "<message><header/><body><session_id>s</session_id></body></message>"
        )
        with pytest.raises(ValueError, match="user_id missing"):
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
            "<email>x@x.com</email><name>X</name><type>private</type>"
            "<user_id>uid-999</user_id><date_of_birth>2006-01-01</date_of_birth>"
            "</customer>"
            "<payment_due><amount>10</amount><status>unpaid</status></payment_due>",
        )
        receiver.process_message(ch, method, None, body)
        ch.basic_ack.assert_called_once_with(delivery_tag=42)
        ch.basic_nack.assert_not_called()

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
        receiver.seen_message_ids["test-msg-001"] = "2026-01-01T00:00:00Z"

        body = _xml_bytes("new_registration", "<customer/>", message_id="test-msg-001")
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
        ch.basic_nack.assert_called_once_with(delivery_tag=42, requeue=False)
        mock_send_error.assert_called_once()
        assert mock_send_error.call_args[0][0] == "odoo_api_error"

    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    @patch("receiver.validate_xml")
    def test_nacks_on_missing_type_field(self, mock_validate, mock_odoo, mock_send_error, ch, method):
        body = (
            b'<?xml version="1.0"?>'
            b"<message>"
            b"<header><message_id>no-type-msg</message_id></header>"
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
            "<user_id>uid-cancel</user_id><session_id>s1</session_id>",
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
        mock_send_error.assert_called_once_with(
            error_code="badge_not_found",
            related_message_id="test-msg-001",
            error_description="Badge BADGE-X not found in local Odoo cache.",
        )
