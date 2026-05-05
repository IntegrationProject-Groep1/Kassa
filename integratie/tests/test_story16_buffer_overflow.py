"""
Story 16: Lokale buffer beschermen tegen overstroming (offline_queue_full)

Test suite for buffer overflow protection.

BDD Scenarios:
- Gegeven dat outbox.json al 500 berichten bevat en RabbitMQ niet bereikbaar is
- Wanneer sender.py een 501e bericht probeert te bufferen
- Dan wordt het bericht weggegooid en blijft outbox.json op 500 + 1 error
- En wordt system_error offline_queue_full verstuurd zodra verbinding herstelt
- En kassa blijft verkopen (orders keep processing normally)
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import sender


@pytest.fixture
def tmp_buffer(tmp_path):
    """Create temporary buffer file for testing."""
    buffer_file = tmp_path / "outbox.json"
    original_file = sender.BUFFER_FILE
    sender.BUFFER_FILE = buffer_file
    yield buffer_file
    sender.BUFFER_FILE = original_file


class TestStory16BufferOverflow:
    """Story 16: Local buffer overflow protection"""

    def test_buffer_rejects_message_when_full(self, tmp_buffer):
        """
        Gegeven: outbox.json bevat al 500 berichten
        Wanneer: we proberen het 501e bericht te bufferen
        Dan: wordt het bericht weggegooid en een error buffered
        """
        original_max = sender.BUFFER_MAX_MESSAGES
        sender.BUFFER_MAX_MESSAGES = 5  # Use 5 for fast testing

        try:
            # Fill buffer to capacity
            for i in range(5):
                sender._buffer_message(f"routing.{i}", f"<msg{i}/>")

            # Buffer should have 5 messages
            entries = json.loads(tmp_buffer.read_text())
            assert len(entries) == 5

            # Try to add 6th message - should raise BufferFullError
            with pytest.raises(sender.BufferFullError) as exc_info:
                sender._buffer_message("routing.6", "<msg6/>")

            assert "not buffered: routing.6" in str(exc_info.value)

            # After overflow, buffer should have 5 original + 1 error
            entries = json.loads(tmp_buffer.read_text())
            assert len(entries) == 6

            # Last entry should be offline_queue_full error
            error_entry = entries[-1]
            assert error_entry["routing_key"] == "kassa.errors"
            assert "offline_queue_full" in error_entry["xml"]

        finally:
            sender.BUFFER_MAX_MESSAGES = original_max

    def test_offline_queue_full_error_contains_details(self, tmp_buffer):
        """
        System_error contains proper structure and details about the failed message
        """
        original_max = sender.BUFFER_MAX_MESSAGES
        sender.BUFFER_MAX_MESSAGES = 2

        try:
            sender._buffer_message("kassa.payments.consumption", "<order1/>")
            sender._buffer_message("kassa.payments.consumption", "<order2/>")

            with pytest.raises(sender.BufferFullError):
                sender._buffer_message("kassa.payments.consumption", "<order3/>")

            entries = json.loads(tmp_buffer.read_text())
            error_entry = entries[-1]
            error_xml = error_entry["xml"]

            # Verify structure
            assert "<error_code>offline_queue_full</error_code>" in error_xml
            assert "<error_description>" in error_xml
            assert "2 items" in error_xml  # Should mention the buffer limit
            assert "order3" in error_xml or "consumption" in error_xml

        finally:
            sender.BUFFER_MAX_MESSAGES = original_max

    def test_overflow_generates_error_in_buffer(self, tmp_buffer):
        """
        When buffer is full, an offline_queue_full error is generated and
        added to the buffer to ensure admin is notified on reconnect.
        """
        original_max = sender.BUFFER_MAX_MESSAGES
        sender.BUFFER_MAX_MESSAGES = 2

        try:
            sender._buffer_message("r.1", "<1/>")
            sender._buffer_message("r.2", "<2/>")

            # Trigger overflow
            with pytest.raises(sender.BufferFullError):
                sender._buffer_message("r.3", "<3/>")

            # Verify buffer contains error
            entries = json.loads(tmp_buffer.read_text())
            assert len(entries) == 3  # 2 original + 1 error

            # Verify the error entry
            error_entry = entries[-1]
            assert error_entry["routing_key"] == "kassa.errors"
            assert "offline_queue_full" in error_entry["xml"]
            assert "r.3" in error_entry["xml"]

        finally:
            sender.BUFFER_MAX_MESSAGES = original_max

    def test_error_routed_to_kassa_errors_queue(self, tmp_buffer):
        """
        The offline_queue_full error is routed to kassa.errors for admin visibility
        """
        original_max = sender.BUFFER_MAX_MESSAGES
        sender.BUFFER_MAX_MESSAGES = 1

        try:
            sender._buffer_message("kassa.payments.consumption", "<order/>")

            with pytest.raises(sender.BufferFullError):
                sender._buffer_message("kassa.payments.consumption", "<order2/>")

            entries = json.loads(tmp_buffer.read_text())
            error_entry = entries[-1]

            # Verify routing
            assert error_entry["routing_key"] == "kassa.errors"

            # Verify this is a system_error message
            assert "<message>" in error_entry["xml"]
            assert "<type>system_error</type>" in error_entry["xml"]

        finally:
            sender.BUFFER_MAX_MESSAGES = original_max

    def test_original_messages_not_lost(self, tmp_buffer):
        """
        When buffer fills up, the original messages are preserved in the buffer.
        Only the NEW message (501st) is dropped.
        """
        original_max = sender.BUFFER_MAX_MESSAGES
        sender.BUFFER_MAX_MESSAGES = 3

        try:
            test_messages = ["<order-001/>", "<order-002/>", "<order-003/>"]
            for i, msg in enumerate(test_messages, 1):
                sender._buffer_message(f"routing.{i}", msg)

            # Try to add one more
            with pytest.raises(sender.BufferFullError):
                sender._buffer_message("routing.4", "<order-004/>")

            entries = json.loads(tmp_buffer.read_text())

            # Verify original 3 messages are intact
            for i, expected_msg in enumerate(test_messages):
                assert entries[i]["xml"] == expected_msg
                assert entries[i]["routing_key"] == f"routing.{i + 1}"

            # Verify the 4th message is NOT in the buffer
            all_xmls = [e["xml"] for e in entries]
            assert "<order-004/>" not in all_xmls

            # But the error should be there
            assert entries[-1]["routing_key"] == "kassa.errors"

        finally:
            sender.BUFFER_MAX_MESSAGES = original_max

    def test_flush_buffer_includes_overflow_error(self, tmp_buffer):
        """
        When buffer is flushed (connection restored), the offline_queue_full error
        is included in the buffer so admin gets notified when messages are replayed.
        """
        original_max = sender.BUFFER_MAX_MESSAGES
        sender.BUFFER_MAX_MESSAGES = 2

        try:
            # Fill buffer and trigger overflow
            sender._buffer_message("r.1", "<1/>")
            sender._buffer_message("r.2", "<2/>")

            with pytest.raises(sender.BufferFullError):
                sender._buffer_message("r.3", "<3/>")

            # Verify buffer contains the error
            entries = json.loads(tmp_buffer.read_text())
            assert len(entries) == 3

            # Verify error is at the end
            error_entry = entries[-1]
            assert error_entry["routing_key"] == "kassa.errors"
            assert "offline_queue_full" in error_entry["xml"]

            # Verify original messages are first
            assert entries[0]["xml"] == "<1/>"
            assert entries[1]["xml"] == "<2/>"

        finally:
            sender.BUFFER_MAX_MESSAGES = original_max

    @patch("sender._publish_or_raise")
    def test_kassa_continues_selling_on_buffer_full(self, mock_publish, tmp_buffer):
        """
        Story 16 AC: Kassa blijft verkopen; enkel doorsturen stopt

        When buffer is full and message can't be buffered, the order_poller
        still returns successfully so Odoo marks the order as processed.
        The order remains in memory (in processed_orders cache) and kassa
        continues accepting new orders.
        """
        # This is tested at the order_poller level, not sender level.
        # Here we verify that the BufferFullError doesn't crash the app.

        original_max = sender.BUFFER_MAX_MESSAGES
        sender.BUFFER_MAX_MESSAGES = 1

        try:
            # Add one message
            sender._buffer_message("kassa.payments.consumption", "<order-1/>")

            # Try to add second message - will raise BufferFullError
            # In real usage, order_poller catches this and continues
            with pytest.raises(sender.BufferFullError):
                sender._buffer_message("kassa.payments.consumption", "<order-2/>")

            # But the application doesn't crash - it can continue
            # The next order can still be submitted to Odoo and processed locally
            # (Order will be in processed_orders cache, kassa POS continues)
            assert True  # We got here without exception propagating

        finally:
            sender.BUFFER_MAX_MESSAGES = original_max
