# test_sender.py – Unit tests for sender.py (RabbitMQ publisher & Buffer)
# Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026

import json
from unittest.mock import MagicMock, patch
import pytest

import sender

# Mock the environment or constants before usage if needed
# We'll use tmp_path to override BUFFER_FILE for outbox tests


@pytest.fixture
def tmp_buffer(tmp_path):
    buffer_file = tmp_path / "outbox.json"
    original_file = sender.BUFFER_FILE
    sender.BUFFER_FILE = buffer_file
    yield buffer_file
    sender.BUFFER_FILE = original_file


class TestSenderBuffer:

    def test_buffer_message_appends(self, tmp_buffer):
        # Buffer first message
        sender._buffer_message("test.routing", "<xml/>", record_id=123)
        entries = json.loads(tmp_buffer.read_text())
        assert len(entries) == 1
        assert entries[0]["routing_key"] == "test.routing"
        assert entries[0]["record_id"] == 123

        # Buffer second
        sender._buffer_message("test.routing.2", "<xml><two/></xml>")
        entries = json.loads(tmp_buffer.read_text())
        assert len(entries) == 2

    def test_buffer_full_raises_error(self, tmp_buffer):
        # Mock max size to 2 for quick testing
        original_max = sender.BUFFER_MAX_MESSAGES
        sender.BUFFER_MAX_MESSAGES = 2

        try:
            sender._buffer_message("r.1", "<1/>")
            sender._buffer_message("r.2", "<2/>")
            # 3rd should fail and create error notification
            with pytest.raises(sender.BufferFullError):
                sender._buffer_message("r.3", "<3/>")

            # Verify buffer contains: 2 original + 1 offline_queue_full error
            entries = json.loads(tmp_buffer.read_text())
            assert len(entries) == 3

            # Verify the last entry is the offline_queue_full error
            error_entry = entries[-1]
            assert error_entry["routing_key"] == "kassa.errors"
            assert "offline_queue_full" in error_entry["xml"]
            assert "message not buffered: r.3" in error_entry["xml"]

            # Verify the 3rd message itself was NOT buffered
            assert entries[0]["xml"] == "<1/>"
            assert entries[1]["xml"] == "<2/>"

            # Verify deduplication: requesting another buffer when full
            # should not create a duplicate error notification
            error_count_before = sum(
                1 for e in entries if e.get("routing_key") == "kassa.errors"
            )
            assert error_count_before == 1

            with pytest.raises(sender.BufferFullError):
                sender._buffer_message("r.4", "<4/>")

            # Reload entries from file
            entries_after = json.loads(tmp_buffer.read_text())

            # Verify no duplicate error was added (still only 1 error + 2 originals)
            error_count_after = sum(
                1 for e in entries_after if e.get("routing_key") == "kassa.errors"
            )
            assert error_count_after == 1
            assert len(entries_after) == 3  # Still 2 original + 1 error
        finally:
            sender.BUFFER_MAX_MESSAGES = original_max

    @patch("sender._publish_or_raise")
    def test_flush_buffer_success(self, mock_send, tmp_buffer):
        sender._buffer_message("r.1", "<1/>", record_id=10)
        sender._buffer_message("r.2", "<2/>", record_id=20)

        mock_send.return_value = None

        success_ids = sender.flush_buffer()
        assert success_ids == [("pos.order", 10), ("pos.order", 20)]
        assert not tmp_buffer.exists()
        assert mock_send.call_count == 2

    @patch("sender._publish_or_raise")
    def test_flush_buffer_stops_on_failure(self, mock_send, tmp_buffer):
        sender._buffer_message("r.1", "<1/>", record_id=10)
        sender._buffer_message("r.2", "<2/>", record_id=20)

        # First succeeds, second raises exception
        mock_send.side_effect = [None, Exception("Broker offline")]

        success_ids = sender.flush_buffer()
        assert success_ids == [("pos.order", 10)]

        # Buffer should still exist and contain the un-flushed item
        entries = json.loads(tmp_buffer.read_text())
        assert len(entries) == 1
        assert entries[0]["routing_key"] == "r.2"

    @patch("sender._publish_or_raise")
    def test_send_message_no_buffer_on_fail(self, mock_send, tmp_buffer):
        mock_send.side_effect = Exception("Broker offline")

        # Send with buffer_on_fail=False
        result = sender.send_message("test.key", "<xml/>", buffer_on_fail=False)

        assert result is False
        assert not tmp_buffer.exists()  # Should NOT have been buffered


class TestSenderXMLBuilders:

    def test_build_wallet_balance_update_xml(self):
        xml_out = sender.build_wallet_balance_update_xml("uid-555", 15.5)
        assert "<type>wallet_balance_update</type>" in xml_out
        assert "<user_id>uid-555</user_id>" in xml_out
        assert '<wallet_balance currency="eur">15.50</wallet_balance>' in xml_out

    def test_build_badge_assigned_xml(self):
        xml_out = sender.build_badge_assigned_xml("B-01", "user@example.com")
        assert "<type>badge_assigned</type>" in xml_out
        assert "<badge_id>B-01</badge_id>" in xml_out
        assert "<email>user@example.com</email>" in xml_out


class TestSenderPublishing:

    @patch("sender.connect_to_rabbitmq")
    def test_publish_or_raise_success(self, mock_connect):
        mock_conn = MagicMock()
        mock_chan = MagicMock()
        mock_connect.return_value = (mock_conn, mock_chan)

        sender._publish_or_raise("route.key", "<msg/>")
        mock_chan.basic_publish.assert_called_once()
        assert mock_chan.basic_publish.call_args[1]["routing_key"] == "route.key"
        assert mock_chan.basic_publish.call_args[1]["exchange"] == sender.EXCHANGE_NAME

    @patch("sender.connect_to_rabbitmq")
    def test_publish_or_raise_custom_exchange(self, mock_connect):
        mock_conn = MagicMock()
        mock_chan = MagicMock()
        mock_connect.return_value = (mock_conn, mock_chan)

        sender._publish_or_raise("route.key", "<msg/>", exchange="my.exchange")
        mock_chan.basic_publish.assert_called_once()
        assert mock_chan.basic_publish.call_args[1]["exchange"] == "my.exchange"

    @patch("sender.connect_to_rabbitmq")
    def test_send_error_to_queue(self, mock_connect):
        mock_conn = MagicMock()
        mock_chan = MagicMock()
        mock_connect.return_value = (mock_conn, mock_chan)

        sender.send_error_to_queue("my_err", "msg-123", "detail")
        mock_chan.basic_publish.assert_called_once()

        pub_kw = mock_chan.basic_publish.call_args[1]
        assert pub_kw["routing_key"] == "kassa.errors"

        # Verify XML payload
        xml_body = pub_kw["body"].decode()
        assert "<type>system_error</type>" in xml_body
        assert "<error_code>my_err</error_code>" in xml_body
        assert "<related_message_id>msg-123</related_message_id>" in xml_body

    @patch("sender._validate_outgoing")
    @patch("sender.send_message")
    def test_send_typed_message_routes_correctly(self, mock_send, mock_validate):
        # Known type => predefined routing key
        sender.send_typed_message("refund_processed", "<xml/>")
        mock_send.assert_called_once_with("kassa.payments.refund", "<xml/>",
                                          record_id=None, model='pos.order', buffer_on_fail=True, exchange=None)

        mock_send.reset_mock()

        # Unknown type => kassa.misc.{type}
        sender.send_typed_message("unknown_type", "<xml/>")
        mock_send.assert_called_once_with("kassa.misc.unknown_type", "<xml/>",
                                          record_id=None, model='pos.order', buffer_on_fail=True, exchange=None)


def test_send_typed_message_buffers_on_xsd_error():
    """XSD validation failure should still buffer the message to prevent data loss."""
    invalid_xml = "<message><invalid/></message>"

    with patch('sender._validate_outgoing') as mock_val, \
         patch('sender._buffer_message') as mock_buffer, \
         patch('sender.send_error_to_queue') as mock_err:

        mock_val.side_effect = ValueError("Mock XSD Error")

        with pytest.raises(sender.XSDValidationError):
            sender.send_typed_message("consumption_order", invalid_xml, record_id=123)

        # Verify it was buffered despite the validation error
        mock_buffer.assert_called_once()
        args = mock_buffer.call_args[0]
        assert args[0] == "kassa.payments.consumption"
        assert args[1] == invalid_xml
        assert mock_buffer.call_args[1]['record_id'] == 123

        # Verify system error was sent
        mock_err.assert_called_once()
