import logging
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import pika

class RabbitMQLogHandler(logging.Handler):
    """
    Centralized Python logging handler that forwards formatted XML logs
    to the RabbitMQ 'logs' queue following the Section 3.5 contract.
    """
    def __init__(self, source_system="kassa"):
        super().__init__()
        self.source_system = source_system
        self._recursion_guard = False

    def emit(self, record):
        if self._recursion_guard:
            return

        # Filter out low-level noise
        if (
            record.name.startswith("pika") or
            record.name.startswith("rabbitmq") or
            record.name == __name__ or
            (record.msg and any(noise in str(record.msg) for noise in [
                "pika", "connection", "channel", "AMQP", "heartbeat", "log_handler"
            ]))
        ):
            return

        self._recursion_guard = True
        try:
            level = "info"
            if record.levelno >= logging.ERROR:
                level = "error"
            elif record.levelno >= logging.WARNING:
                level = "warning"

            action = getattr(record, "action", "system_error")
            valid_actions = {
                "registration", "user", "payment", "invoice", "session", "calendar",
                "email", "wallet", "refund", "identity", "xml_validation", "system_error", "badge"
            }
            if action not in valid_actions:
                action = "system_error"

            message = self.format(record)

            # Build XML
            root = ET.Element("message")
            header = ET.SubElement(root, "header")
            ET.SubElement(header, "message_id").text = str(uuid.uuid4())
            ET.SubElement(header, "timestamp").text = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            ET.SubElement(header, "source").text = self.source_system
            ET.SubElement(header, "type").text = "log"
            ET.SubElement(header, "version").text = "2.0"

            body = ET.SubElement(root, "body")
            ET.SubElement(body, "level").text = level
            ET.SubElement(body, "action").text = action
            ET.SubElement(body, "message").text = message

            xml_str = ET.tostring(root, encoding="utf-8")

            # Load variables using config_utils dynamically to handle late environment loading
            from config_utils import get_env, parse_rabbit_port

            host = get_env("RABBIT_HOST") or get_env("RABBITMQ_HOST", "localhost")
            port = parse_rabbit_port()
            user = get_env("RABBIT_USER") or get_env("RABBITMQ_USER", "guest")
            passwd = get_env("RABBIT_PASS") or get_env("RABBITMQ_PASS") or get_env("RABBITMQ_PASSWORD", "guest")
            vhost = get_env("RABBIT_VHOST") or get_env("RABBITMQ_VHOST", "/")

            credentials = pika.PlainCredentials(user, passwd)
            parameters = pika.ConnectionParameters(
                host=host,
                port=port,
                virtual_host=vhost,
                credentials=credentials,
                connection_attempts=1,
                retry_delay=1,
            )

            # Oneshot connection
            connection = pika.BlockingConnection(parameters)
            try:
                channel = connection.channel()
                channel.queue_declare(queue="logs", durable=True)
                channel.basic_publish(
                    exchange="",
                    routing_key="logs",
                    body=xml_str,
                    properties=pika.BasicProperties(
                        content_type="application/xml",
                        delivery_mode=2
                    )
                )
            finally:
                connection.close()
        except Exception:
            pass
        finally:
            self._recursion_guard = False
