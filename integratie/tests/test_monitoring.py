"""
test_monitoring.py — Comprehensive tests for the Monitoring/Logging system.
"""

import pytest
from unittest.mock import MagicMock, patch
from monitoring import MonitoringManager, monitor
from sender import build_log_xml, _validate_outgoing, XSDValidationError

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
        assert f"<level>info</level>" in xml
        assert f"<action>{action}</action>" in xml
        assert f"<message>Test {action}</message>" in xml
        
        # Ensure it passes strict XSD validation
        _validate_outgoing("log", xml)

def test_build_log_xml_error_level():
    """Verify error level logging also validates."""
    xml = build_log_xml(level="error", action="system_error", message="Critical Failure")
    _validate_outgoing("log", xml)
    assert "<level>error</level>" in xml

@patch("monitoring.send_typed_message")
def test_monitoring_log_call_params(mock_send):
    """Verify monitor.log calls send_typed_message with EXACT conformant parameters."""
    monitor.log("warning", "xml_validation", "Broken XML from CRM")
    
    mock_send.assert_called_once()
    args, kwargs = mock_send.call_args
    assert kwargs["msg_type"] == "log"
    assert kwargs["exchange"] == ""  # MUST go to default exchange
    assert kwargs["buffer_on_fail"] is False  # MUST NOT buffer (transient)
    assert "<level>warning</level>" in kwargs["message_xml"]
    assert "<action>xml_validation</action>" in kwargs["message_xml"]
    assert "Broken XML from CRM" in kwargs["message_xml"]

def test_invalid_log_action_fails_xsd():
    """Verify that an action not in the XSD enum correctly raises a validation error."""
    # This prevents us from sending non-conformant data that the monitoring team can't parse
    xml = build_log_xml("info", "invalid_action_name", "Should fail")
    
    with pytest.raises(ValueError, match="XSD Validation Error"):
        _validate_outgoing("log", xml)

@patch("monitoring.send_typed_message")
def test_monitor_log_exception_handling(mock_send):
    """Verify that a failure in sending a log does NOT raise an exception (non-blocking)."""
    mock_send.side_effect = Exception("RabbitMQ Down")
    
    # This should NOT raise even if RabbitMQ is down, just log a warning locally
    monitor.log("info", "payment", "This should not crash the app")
    mock_send.assert_called_once()

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
