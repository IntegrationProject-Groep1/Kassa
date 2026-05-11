# -*- coding: utf-8 -*-
import os
import uuid
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


def _build_wallet_lease_request_xml(identity_uuid: str) -> str:
    """Minimal wallet_lease_request without badge_id (QR scan path)."""
    root = ET.Element("message")
    header = ET.SubElement(root, "header")
    ET.SubElement(header, "message_id").text = str(uuid.uuid4())
    ET.SubElement(header, "timestamp").text = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ET.SubElement(header, "source").text = "kassa"
    ET.SubElement(header, "type").text = "wallet_lease_request"
    ET.SubElement(header, "version").text = "1.0"
    body = ET.SubElement(root, "body")
    ET.SubElement(body, "identity_uuid").text = identity_uuid
    return '<?xml version="1.0" encoding="UTF-8"?>' + ET.tostring(root, encoding="unicode")


def _publish_lease_request(identity_uuid: str) -> None:
    """Publish wallet_lease_request to RabbitMQ via a short-lived pika connection."""
    try:
        import pika  # noqa: PLC0415
    except ImportError:
        _logger.error("[Kassa QR] pika not installed — cannot publish wallet_lease_request")
        return

    host    = os.environ.get("RABBIT_HOST", "rabbitmq")
    port    = int(os.environ.get("RABBIT_PORT", "5672"))
    user    = os.environ.get("RABBIT_USER", "guest")
    passwd  = os.environ.get("RABBIT_PASS", "guest")
    vhost   = os.environ.get("RABBIT_VHOST", "/")
    exchange = os.environ.get("RABBIT_EXCHANGE", "kassa.exchange")

    xml_body = _build_wallet_lease_request_xml(identity_uuid)

    try:
        credentials = pika.PlainCredentials(user, passwd)
        params = pika.ConnectionParameters(
            host=host, port=port, virtual_host=vhost,
            credentials=credentials,
            connection_attempts=2, retry_delay=1, socket_timeout=5,
        )
        conn = pika.BlockingConnection(params)
        channel = conn.channel()
        channel.basic_publish(
            exchange=exchange,
            routing_key="kassa.to.crm.wallet_lease_request",
            body=xml_body.encode("utf-8"),
            properties=pika.BasicProperties(content_type="application/xml", delivery_mode=2),
        )
        conn.close()
        _logger.info("[Kassa QR] wallet_lease_request published for %s", identity_uuid)
    except Exception as exc:
        _logger.error("[Kassa QR] Failed to publish wallet_lease_request: %s", exc)


class KassaQrController(http.Controller):

    @http.route("/kassa/qr_scan", type="json", auth="user", methods=["POST"], csrf=False)
    def qr_scan(self, identity_uuid=None, **kwargs):
        if not identity_uuid:
            return {"status": "error", "message": "identity_uuid is vereist."}

        env = request.env
        partner = env["res.partner"].search([("x_user_id", "=", identity_uuid)], limit=1)

        created = False
        if not partner:
            partner = env["res.partner"].create({
                "name": f"QR Bezoeker ({identity_uuid[:8]})",
                "x_user_id": identity_uuid,
                "customer_rank": 1,
            })
            created = True
            _logger.info("[Kassa QR] Created placeholder partner %s for uuid %s", partner.id, identity_uuid)

        if partner.x_lease_active:
            return {"status": "already_active", "partner_id": partner.id, "partner_name": partner.name}

        _publish_lease_request(identity_uuid)

        status = "not_found_and_created" if created else "lease_requested"
        return {"status": status, "partner_id": partner.id, "partner_name": partner.name}
