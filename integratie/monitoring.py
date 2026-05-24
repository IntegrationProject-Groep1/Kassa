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
        """Send a conformant log message by routing to Python standard logging."""
        lvl_num = logging.INFO
        if level == "warning":
            lvl_num = logging.WARNING
        elif level == "error":
            lvl_num = logging.ERROR

        logging.getLogger("kassa.monitoring").log(lvl_num, message, extra={"action": action})


# Global singleton instance for easy access
monitor = MonitoringManager()
