"""
test_monitoring.py — Comprehensive tests for the Monitoring/Logging system.
"""

import pytest
from unittest.mock import patch
from monitoring import MonitoringManager, monitor
from sender import build_log_xml, _validate_outgoing


def test_monitoring_manager_singleton():
    """Verify MonitoringManager is a singleton."""
    m1 = MonitoringManager()
    m2 = MonitoringManager()
    assert m1 is m2
    assert m1 is monitor


def test_build_log_xml_valid():
    """Verify log XML structure and validation for all standard actions."""
    actions = ["payment", "xml_validation", "system_error", "session", "identity"]
    for action in actions:
        xml = build_log_xml(level="info", action=action, message=f"Test {action}")
        assert "<level>info</level>" in xml
        assert f"<action>{action}</action>" in xml
        assert f"<message>Test {action}</message>" in xml

        # Ensure it passes strict XSD validation
        _validate_outgoing("log", xml)


def test_build_log_xml_error_level():
    """Verify error level logging also validates."""
    xml = build_log_xml(level="error", action="system_error", message="Critical Failure")
    _validate_outgoing("log", xml)
    assert "<level>error</level>" in xml


@patch("rabbitmq_log_handler.pika.BlockingConnection")
def test_monitoring_log_call_params(mock_blocking_connection):
    """Verify monitor.log routes through standard logger and RabbitMQLogHandler publishes correct XML."""
    from rabbitmq_log_handler import RabbitMQLogHandler
    import logging

    logger = logging.getLogger("kassa.monitoring")
    handler = RabbitMQLogHandler(source_system="kassa")
    logger.addHandler(handler)
    try:
        mock_conn = mock_blocking_connection.return_value
        mock_chan = mock_conn.channel.return_value

        monitor.log("warning", "xml_validation", "Broken XML from CRM")

        mock_blocking_connection.assert_called_once()
        mock_chan.basic_publish.assert_called_once()
        kwargs = mock_chan.basic_publish.call_args[1]
        assert kwargs["routing_key"] == "logs"
        assert kwargs["exchange"] == ""
        xml_body = kwargs["body"].decode("utf-8")
        assert "<level>warning</level>" in xml_body
        assert "<action>xml_validation</action>" in xml_body
        assert "Broken XML from CRM" in xml_body
    finally:
        logger.removeHandler(handler)


def test_invalid_log_action_fails_xsd():
    """Verify that an action not in the XSD enum correctly raises a validation error."""
    # This prevents us from sending non-conformant data that the monitoring team can't parse
    xml = build_log_xml("info", "invalid_action_name", "Should fail")

    with pytest.raises(ValueError, match="XSD Validation Error"):
        _validate_outgoing("log", xml)


@patch("rabbitmq_log_handler.pika.BlockingConnection")
def test_monitor_log_exception_handling(mock_blocking_connection):
    """Verify that a failure in sending a log does NOT raise an exception (non-blocking)."""
    from rabbitmq_log_handler import RabbitMQLogHandler
    import logging

    mock_blocking_connection.side_effect = Exception("RabbitMQ Down")
    logger = logging.getLogger("kassa.monitoring")
    handler = RabbitMQLogHandler(source_system="kassa")
    logger.addHandler(handler)
    try:
        # This should NOT raise even if RabbitMQ is down
        monitor.log("info", "payment", "This should not crash the app")
    finally:
        logger.removeHandler(handler)


@patch("sender._publish_or_raise")
def test_send_typed_message_exchange_override(mock_publish):
    """Verify send_typed_message correctly passes the exchange override to _publish_or_raise."""
    from sender import send_typed_message

    # Test with custom exchange (used for logs)
    xml = build_log_xml("info", "payment", "test")
    send_typed_message("log", xml, exchange="")

    mock_publish.assert_called_once()
    # Check that it called with exchange=""
    assert mock_publish.call_args[1]["exchange"] == ""
