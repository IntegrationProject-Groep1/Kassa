"""
monitoring.py — High-level API for Monitoring (Logging).
Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026

This module provides a unified way to report status and errors to the
centralized monitoring team using XML over RabbitMQ (Contract v2.3).
"""

import threading
import logging
from typing import Literal

from sender import (
    build_log_xml,
    send_typed_message
)


logger = logging.getLogger(__name__)

# Valid levels and actions according to Section 3.5 of the contract.
LogLevel = Literal["info", "warning", "error"]
LogAction = Literal[
    "registration", "user", "payment", "invoice", "session",
    "calendar", "email", "wallet", "refund", "identity",
    "xml_validation", "system_error", "badge"
]


class MonitoringManager:
    """
    Manages monitoring tasks: application logging to the monitoring team.
    Designed to be used as a singleton within the integration service.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Enforce singleton: only one MonitoringManager exists per process.

        Opening a new pika connection for every log call would be expensive and
        would exhaust RabbitMQ connection limits under high traffic. The singleton
        reuses a single channel for all log messages.
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(MonitoringManager, cls).__new__(cls)
            return cls._instance

    def log(self, level: LogLevel, action: LogAction, message: str):
        """Send a conformant log message to the monitoring team via RabbitMQ.

        The message is built using ``build_log_xml`` and validated against the
        ``schema_log.xsd`` contract before being published.  It is sent on the
        default exchange (``""``) to the ``logs`` queue — direct queue routing,
        not the Kassa topic exchange.

        Logs are NOT buffered when the broker is unreachable (``buffer_on_fail=False``).
        Transient log loss is acceptable; a failed log should not fill the offline
        outbox and delay business messages (orders, payments, wallet updates).

        Args:
            level:   Severity — ``"info"``, ``"warning"``, or ``"error"``.
            action:  Message category from the contract's allowed-action list,
                     e.g. ``"payment"``, ``"wallet"``, ``"xml_validation"``.
            message: Human-readable description, truncated by the XSD at 1000 chars.
        """
        try:
            xml = build_log_xml(level, action, message)
            # Logs are important status updates, but usually transient.
            # We don't buffer them by default to avoid filling the outbox with logs.
            send_typed_message(
                msg_type="log",
                message_xml=xml,
                buffer_on_fail=False,
                exchange=""
            )
            logger.info(f"📡 Monitor Log [{level.upper()}] {action}: {message}")
        except Exception as e:
            logger.warning(f"Could not send monitor log: {e}")


# Global singleton instance for easy access
monitor = MonitoringManager()
