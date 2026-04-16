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
        sender._buffer_message("test.routing", "<xml/>", order_id=123)
        entries = json.loads(tmp_buffer.read_text())
        assert len(entries) == 1
        assert entries[0]["routing_key"] == "test.routing"
        assert entries[0]["order_id"] == 123

        # Buffer second
        sender._buffer_message("test.routing.2", "<xml><two/></xml>")
        entries = json.loads(tmp_buffer.read_text())
        assert len(entries) == 2

    @patch("sender.send_error_to_queue")
    def test_buffer_full_raises_error(self, mock_error_queue, tmp_buffer):
        # Mock max size to 2 for quick testing
        original_max = sender.BUFFER_MAX_MESSAGES
        sender.BUFFER_MAX_MESSAGES = 2

        try:
            sender._buffer_message("r.1", "<1/>")
            sender._buffer_message("r.2", "<2/>")
            # 3rd should fail
            with pytest.raises(sender.BufferFullError):
                sender._buffer_message("r.3", "<3/>")

            mock_error_queue.assert_called_once()
        finally:
            sender.BUFFER_MAX_MESSAGES = original_max

    @patch("sender.send_message")
    def test_flush_buffer_success(self, mock_send, tmp_buffer):
        sender._buffer_message("r.1", "<1/>", order_id=10)
        sender._buffer_message("r.2", "<2/>", order_id=20)

        mock_send.return_value = True

        success_ids = sender.flush_buffer()
        assert success_ids == [10, 20]
        assert not tmp_buffer.exists()
        assert mock_send.call_count == 2

    @patch("sender.send_message")
    def test_flush_buffer_stops_on_failure(self, mock_send, tmp_buffer):
        sender._buffer_message("r.1", "<1/>", order_id=10)
        sender._buffer_message("r.2", "<2/>", order_id=20)

        # First succeeds, second raises exception
        mock_send.side_effect = [True, Exception("Broker offline")]

        success_ids = sender.flush_buffer()
        assert success_ids == [10]

        # Buffer should still exist and contain the un-flushed item
        entries = json.loads(tmp_buffer.read_text())
        assert len(entries) == 1
        assert entries[0]["routing_key"] == "r.2"


class TestSenderXMLBuilders:

    def test_build_wallet_balance_update_xml(self):
        xml_out = sender.build_wallet_balance_update_xml("uid-555", 15.5)
        assert "<type>wallet_balance_update</type>" in xml_out
        assert "<user_id>uid-555</user_id>" in xml_out
        assert '<new_balance currency="eur">15.50</new_balance>' in xml_out

    def test_build_badge_assigned_xml(self):
        xml_out = sender.build_badge_assigned_xml("B-01", "uid-1")
        assert "<type>badge_assigned</type>" in xml_out
        assert "<badge_id>B-01</badge_id>" in xml_out
        assert "<user_id>uid-1</user_id>" in xml_out


class TestSenderPublishing:

    @patch("sender.connect_to_rabbitmq")
    def test_publish_or_raise_success(self, mock_connect):
        mock_conn = MagicMock()
        mock_chan = MagicMock()
        mock_connect.return_value = (mock_conn, mock_chan)

        sender._publish_or_raise("route.key", "<msg/>")
        mock_chan.basic_publish.assert_called_once()
        assert mock_chan.basic_publish.call_args[1]["routing_key"] == "route.key"

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
        mock_send.assert_called_once_with("kassa.payments.refund", "<xml/>", order_id=None)

        mock_send.reset_mock()

        # Unknown type => kassa.misc.{type}
        sender.send_typed_message("unknown_type", "<xml/>")
        mock_send.assert_called_once_with("kassa.misc.unknown_type", "<xml/>", order_id=None)
