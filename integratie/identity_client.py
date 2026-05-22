"""
identity_client.py — RPC client for the central Identity Service

Implements the RPC request/reply pattern over RabbitMQ for the following
flat-XML Identity messages (no <message><header><body> envelope):

- identity.user.create.request
- identity.user.lookup.email.request
- identity.user.lookup.uuid.request

The caller must provide queue/exchange routing via environment variables so
operations can configure the actual broker routing. Retries and correlation
validation are implemented here.
"""
import os
import time
import uuid
import logging
import xml.etree.ElementTree as ET
from typing import Tuple, Optional, Dict

import pika
from defusedxml import ElementTree as DET
from lxml import etree

from config_utils import require_env, parse_rabbit_port

RABBIT_PORT = parse_rabbit_port()
RABBIT_VHOST = os.environ.get("RABBIT_VHOST", "/")

logger = logging.getLogger(__name__)

_SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "schemas")
_IDENTITY_RESPONSE_SCHEMA_PATH = os.path.join(_SCHEMA_DIR, "schema_identity_response.xsd")
_IDENTITY_REQUEST_SCHEMA_PATH = os.path.join(_SCHEMA_DIR, "schema_identity_request.xsd")
_identity_response_schema: "etree.XMLSchema | None" = None
_identity_request_schema: "etree.XMLSchema | None" = None


def _get_identity_response_schema() -> "etree.XMLSchema | None":
    """Load and cache the XSD schema for Identity Service response messages.

    Parsed once on first access and reused.  Returns ``None`` if the schema
    file cannot be loaded (e.g. during unit tests without the schema directory)
    — callers skip validation in that case rather than crashing.
    """
    global _identity_response_schema
    if _identity_response_schema is None:
        try:
            _identity_response_schema = etree.XMLSchema(etree.parse(_IDENTITY_RESPONSE_SCHEMA_PATH))
        except Exception as exc:
            logger.warning("[IDENTITY] Could not load identity_response XSD: %s", exc)
    return _identity_response_schema


def _get_identity_request_schema() -> "etree.XMLSchema | None":
    """Load and cache the XSD schema for Identity Service request messages.

    Same lazy-load pattern as ``_get_identity_response_schema``.
    Validating outgoing requests before sending prevents sending malformed XML
    to the Identity Service, which would result in an error response or timeout.
    """
    global _identity_request_schema
    if _identity_request_schema is None:
        try:
            _identity_request_schema = etree.XMLSchema(etree.parse(_IDENTITY_REQUEST_SCHEMA_PATH))
        except Exception as exc:
            logger.warning("[IDENTITY] Could not load identity_request XSD: %s", exc)
    return _identity_request_schema


def _validate_request_xml(xml_text: str) -> None:
    """Validate an outgoing Identity request against the request XSD schema.

    Raises ``IdentityError`` if the XML does not conform.  Skips validation
    silently when the schema could not be loaded (schema is optional for tests).
    """
    schema = _get_identity_request_schema()
    if schema is None:
        return
    try:
        doc = etree.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
        if not schema.validate(doc):
            raise IdentityError("Identity request did not pass XSD validation: %s" % schema.error_log)
    except etree.XMLSyntaxError as exc:
        raise IdentityError("Identity request is not valid XML: %s" % exc)


# Configuration — caller may override via environment
IDENTITY_ROUTING_KEY_CREATE = os.environ.get(
    "IDENTITY_ROUTING_KEY_CREATE", "identity.user.create.request"
)
IDENTITY_ROUTING_KEY_LOOKUP_EMAIL = os.environ.get(
    "IDENTITY_ROUTING_KEY_LOOKUP_EMAIL", "identity.user.lookup.email.request"
)
IDENTITY_ROUTING_KEY_LOOKUP_UUID = os.environ.get(
    "IDENTITY_ROUTING_KEY_LOOKUP_UUID", "identity.user.lookup.uuid.request"
)

RPC_RETRIES = int(os.environ.get("IDENTITY_RPC_RETRIES", "3"))
RPC_TIMEOUT = float(os.environ.get("IDENTITY_RPC_TIMEOUT_SEC", "5"))


class IdentityError(RuntimeError):
    pass


class IdentityUnavailableError(IdentityError):
    pass


class IdentityEmailAlreadyExists(IdentityError):
    def __init__(self, message: str, email: str):
        super().__init__(message)
        self.email = email


def _build_create_request_xml(email: str, source_system: str) -> str:
    """Build the flat XML body for ``identity.user.create.request``.

    The Identity Service uses a simplified flat-XML format (no ``<message><header><body>``
    envelope) for its own RPC protocol.  ``source_system`` identifies which team
    provisioned the user (e.g. ``"kassa"``), stored by the Identity Service for audit.
    """
    root = ET.Element("identity_request")
    ET.SubElement(root, "email").text = email
    ET.SubElement(root, "source_system").text = source_system
    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")


def _build_lookup_email_xml(email: str) -> str:
    """Build the flat XML body for ``identity.user.lookup.email.request``."""
    root = ET.Element("identity_request")
    ET.SubElement(root, "email").text = email
    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")


def _build_lookup_uuid_xml(master_uuid: str) -> str:
    """Build the flat XML body for ``identity.user.lookup.uuid.request``."""
    root = ET.Element("identity_request")
    ET.SubElement(root, "master_uuid").text = master_uuid
    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")


def connect_to_rabbitmq():
    """Create and return a fresh (conn, channel) pair.

    Exposed at module level so tests can monkeypatch `identity_client.connect_to_rabbitmq`.
    """
    env = require_env("RABBIT_HOST", "RABBIT_USER", "RABBIT_PASS")
    credentials = pika.PlainCredentials(env["RABBIT_USER"], env["RABBIT_PASS"])
    params = pika.ConnectionParameters(
        host=env["RABBIT_HOST"],
        port=RABBIT_PORT,
        virtual_host=RABBIT_VHOST,
        credentials=credentials,
        heartbeat=60,
        blocked_connection_timeout=10,
    )
    conn = pika.BlockingConnection(params)
    channel = conn.channel()
    return conn, channel


def _parse_identity_response(xml_text: str) -> Tuple[str, Dict[str, Optional[str]]]:
    """Return (status, payload_dict). On error status include error_code/message.

    Values in the payload may be None when XML elements are missing, so
    use Optional[str] for dictionary values.
    """
    schema = _get_identity_response_schema()
    if schema is not None:
        try:
            doc = etree.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
            if not schema.validate(doc):
                errors = str(schema.error_log)
                logger.warning("[IDENTITY] identity_response failed XSD validation: %s", errors)
                raise IdentityError("Identity response did not pass XSD validation: %s" % errors)
        except etree.XMLSyntaxError as exc:
            raise IdentityError("Identity response is not valid XML: %s" % exc)

    root = DET.fromstring(xml_text)
    status = (root.findtext("status") or "").strip()
    if status == "ok":
        user_el = root.find("user")
        user = {
            "master_uuid": user_el.findtext("master_uuid") if user_el is not None else None,
            "email": user_el.findtext("email") if user_el is not None else None,
            "created_by": user_el.findtext("created_by") if user_el is not None else None,
            "created_at": user_el.findtext("created_at") if user_el is not None else None,
        }
        return status, user
    else:
        error_code = (root.findtext("error_code") or "").strip()
        message = (root.findtext("message") or "").strip()
        return status, {"error_code": error_code, "message": message}


def _rpc_call(routing_key: str, body_xml: str, timeout: float = RPC_TIMEOUT) -> str:
    """Perform RPC call: publish request and wait synchronously for reply.

    Uses a server-named exclusive reply queue and validates correlation_id
    in the reply. Raises IdentityUnavailableError on timeout.
    """
    attempts = RPC_RETRIES
    for attempt in range(attempts):
        conn = None
        channel = None
        try:
            conn, channel = connect_to_rabbitmq()

            # Declare a temporary exclusive reply queue
            q = channel.queue_declare(queue="", exclusive=True)
            reply_queue = q.method.queue

            correlation_id = str(uuid.uuid4())
            message_id = str(uuid.uuid4())
            props = pika.BasicProperties(
                reply_to=reply_queue,
                correlation_id=correlation_id,
                message_id=message_id,
                timestamp=int(time.time()),
            )

            # Publish — empty exchange targets a queue, or allow routing keys
            channel.basic_publish(
                exchange="",
                routing_key=routing_key,
                body=body_xml.encode("utf-8"),
                properties=props,
            )

            deadline = time.time() + timeout
            while time.time() < deadline:
                method_frame, header_frame, body = channel.basic_get(reply_queue, auto_ack=True)
                if method_frame is None:
                    time.sleep(0.05)
                    continue

                # Validate correlation_id
                resp_corr = getattr(header_frame, "correlation_id", None)
                if resp_corr != correlation_id:
                    logger.warning("[IDENTITY RPC] Ignoring unmatched correlation_id %s", resp_corr)
                    continue

                return body.decode("utf-8")

            # Timeout — try again (will recreate reply queue)
            logger.warning("[IDENTITY RPC] No reply within %.1fs (attempt %d/%d)", timeout, attempt + 1, attempts)
            if attempt < attempts - 1:
                time.sleep(0.5 * (2 ** attempt))
                continue
            raise IdentityUnavailableError("Identity service did not reply within timeout")

        except (pika.exceptions.AMQPError, OSError) as exc:
            logger.warning("[IDENTITY RPC] AMQP error: %s (attempt %d/%d)", exc, attempt + 1, attempts)
            if attempt < attempts - 1:
                time.sleep(0.5 * (2 ** attempt))
                continue
            raise IdentityUnavailableError("Identity service unreachable: %s" % exc)

        finally:
            # Ensure we close the channel and connection to delete the exclusive queue
            try:
                if channel is not None and not getattr(channel, "is_closed", False):
                    try:
                        channel.close()
                    except Exception:
                        pass
                if conn is not None and not getattr(conn, "is_closed", False):
                    try:
                        conn.close()
                    except Exception:
                        pass
            except Exception:
                # Best-effort cleanup; do not mask the original exception
                pass

    # Should never be reached because callers either return a response or
    # an IdentityUnavailableError is raised above, but include an explicit
    # raise to satisfy static analysis.
    raise IdentityUnavailableError("Identity service did not reply")


def create_user(email: str, source_system: str = "frontend") -> str:
    """Call identity.user.create.request and return master_uuid on success.

    Raises IdentityEmailAlreadyExists when error_code is EMAIL_ALREADY_EXISTS (§15.4).
    Raises IdentityUnavailableError when RPC fails or times out.
    Raises IdentityError for other identity errors.
    """
    xml = _build_create_request_xml(email, source_system)
    _validate_request_xml(xml)
    resp_xml = _rpc_call(IDENTITY_ROUTING_KEY_CREATE, xml)
    status, payload = _parse_identity_response(resp_xml)
    if status == "ok":
        master_uuid = payload.get("master_uuid")
        if not master_uuid:
            raise IdentityError("Identity returned ok but no master_uuid present")
        return master_uuid
    else:
        if payload.get("error_code") == "EMAIL_ALREADY_EXISTS":
            msg = payload.get("message") or ""
            raise IdentityEmailAlreadyExists(msg, email)
        raise IdentityError(payload.get("message") or "Unknown identity error")


def lookup_by_email(email: str) -> Optional[Dict[str, Optional[str]]]:
    """Look up an existing Identity user by email address.

    Called in two situations:
    1. PartnerIdentityPoller receives IdentityEmailAlreadyExists from create_user —
       the email is registered but the UUID is not yet in Odoo, so we fetch it here.
    2. OrderPoller last-resort fallback when a partner has an email but no x_user_id
       and create_user raises EMAIL_ALREADY_EXISTS.

    Uses flat XML format (no <message><header><body> envelope) per Identity Service contract.
    Returns the user payload dict on success, or None if the identity was not found.
    """
    xml = _build_lookup_email_xml(email)
    _validate_request_xml(xml)
    resp_xml = _rpc_call(IDENTITY_ROUTING_KEY_LOOKUP_EMAIL, xml)
    status, payload = _parse_identity_response(resp_xml)
    if status == "ok":
        return payload
    logger.warning(
        "[IDENTITY] lookup_by_email failed for %s: error_code=%s message=%s",
        email, payload.get("error_code"), payload.get("message"),
    )
    return None


def lookup_by_uuid(master_uuid: str) -> Optional[Dict[str, Optional[str]]]:
    """Look up an existing Identity user by their master UUID.

    Not used in the primary Kassa flows (receiver and order_poller go by email),
    but provided for completeness and potential future use (e.g. admin tooling or
    cross-service debugging that starts from a known UUID).
    Returns the user payload dict on success, or None if not found.
    """
    xml = _build_lookup_uuid_xml(master_uuid)
    _validate_request_xml(xml)
    resp_xml = _rpc_call(IDENTITY_ROUTING_KEY_LOOKUP_UUID, xml)
    status, payload = _parse_identity_response(resp_xml)
    if status == "ok":
        return payload
    logger.warning(
        "[IDENTITY] lookup_by_uuid failed for %s: error_code=%s message=%s",
        master_uuid, payload.get("error_code"), payload.get("message"),
    )
    return None
