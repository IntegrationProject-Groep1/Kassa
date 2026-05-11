# -*- coding: utf-8 -*-
import json
import os
import uuid
import time
import logging
import xml.etree.ElementTree as ET          # building only
import defusedxml.ElementTree as defused_ET  # safe parsing of external XML
from datetime import datetime, timezone
from typing import List, Dict

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# Seconds to wait for Planning's user_sessions_response before giving up.
_PLANNING_RPC_TIMEOUT = float(os.environ.get("PLANNING_RPC_TIMEOUT", "5"))


# ── XML builders ──────────────────────────────────────────────────────────────

def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_wallet_lease_request_xml(identity_uuid: str) -> str:
    root = ET.Element("message")
    header = ET.SubElement(root, "header")
    ET.SubElement(header, "message_id").text = str(uuid.uuid4())
    ET.SubElement(header, "timestamp").text = _now_utc()
    ET.SubElement(header, "source").text = "kassa"
    ET.SubElement(header, "type").text = "wallet_lease_request"
    ET.SubElement(header, "version").text = "2.0"
    body = ET.SubElement(root, "body")
    ET.SubElement(body, "identity_uuid").text = identity_uuid
    return '<?xml version="1.0" encoding="UTF-8"?>' + ET.tostring(root, encoding="unicode")


def _build_user_sessions_request_xml(identity_uuid: str, correlation_id: str) -> str:
    root = ET.Element("message")
    header = ET.SubElement(root, "header")
    ET.SubElement(header, "message_id").text = str(uuid.uuid4())
    ET.SubElement(header, "timestamp").text = _now_utc()
    ET.SubElement(header, "source").text = "kassa"
    ET.SubElement(header, "type").text = "user_sessions_request"
    ET.SubElement(header, "version").text = "2.0"
    ET.SubElement(header, "correlation_id").text = correlation_id
    body = ET.SubElement(root, "body")
    ET.SubElement(body, "identity_uuid").text = identity_uuid
    return '<?xml version="1.0" encoding="UTF-8"?>' + ET.tostring(root, encoding="unicode")


# ── RabbitMQ helpers ──────────────────────────────────────────────────────────

def _pika_connection():
    """Return (pika_module, BlockingConnection) or (None, None) if pika unavailable."""
    try:
        import pika  # noqa: PLC0415
    except ImportError:
        _logger.warning("[Kassa QR] pika not installed")
        return None, None

    credentials = pika.PlainCredentials(
        os.environ.get("RABBIT_USER", "guest"),
        os.environ.get("RABBIT_PASS", "guest"),
    )
    params = pika.ConnectionParameters(
        host=os.environ.get("RABBIT_HOST", "rabbitmq"),
        port=int(os.environ.get("RABBIT_PORT", "5672")),
        virtual_host=os.environ.get("RABBIT_VHOST", "/"),
        credentials=credentials,
        connection_attempts=2,
        retry_delay=1,
        socket_timeout=5,
    )
    try:
        return pika, pika.BlockingConnection(params)
    except Exception as exc:
        _logger.warning("[Kassa QR] RabbitMQ connection failed: %s", exc)
        return pika, None


def _fetch_sessions_from_planning(identity_uuid: str) -> List[Dict]:
    """
    RPC call to Planning via RabbitMQ.
    Publishes user_sessions_request and waits up to PLANNING_RPC_TIMEOUT seconds
    for user_sessions_response on an exclusive reply queue.
    Returns list of {'session_id': ..., 'title': ...} dicts, or [] on timeout/error.
    """
    pika, conn = _pika_connection()
    if not conn:
        return []

    corr_id = str(uuid.uuid4())
    xml_body = _build_user_sessions_request_xml(identity_uuid, corr_id)
    planning_exchange = os.environ.get("RABBIT_PLANNING_EXCHANGE", "planning.exchange")
    result: List[Dict] = []

    try:
        channel = conn.channel()
        reply_queue = channel.queue_declare(queue="", exclusive=True).method.queue

        def _on_response(ch, method, props, body):
            if props.correlation_id != corr_id:
                return
            try:
                root = defused_ET.fromstring(body)
                body_el = root.find("body")
                if body_el is not None and body_el.findtext("status") == "ok":
                    for session in body_el.findall(".//session"):
                        title = (session.findtext("title") or "").strip()
                        sid = (session.findtext("session_id") or "").strip()
                        if title:
                            result.append({"session_id": sid, "title": title})
            except Exception as exc:
                _logger.warning("[Kassa QR] Could not parse user_sessions_response: %s", exc)

        channel.basic_consume(queue=reply_queue, on_message_callback=_on_response, auto_ack=True)
        channel.basic_publish(
            exchange=planning_exchange,
            routing_key="kassa.to.planning.user_sessions_request",
            body=xml_body.encode("utf-8"),
            properties=pika.BasicProperties(
                content_type="application/xml",
                correlation_id=corr_id,
                reply_to=reply_queue,
            ),
        )

        # Poll for a response until timeout.
        deadline = time.monotonic() + _PLANNING_RPC_TIMEOUT
        while time.monotonic() < deadline and not result:
            remaining = deadline - time.monotonic()
            conn.process_data_events(time_limit=min(0.5, remaining))

        _logger.info(
            "[Kassa QR] Planning RPC: %d session(s) returned for %s",
            len(result), identity_uuid,
        )
    except Exception as exc:
        _logger.warning("[Kassa QR] Planning RPC error: %s", exc)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    return result


def _publish_lease_request(identity_uuid: str) -> None:
    """Fire-and-forget: publish wallet_lease_request to kassa.exchange."""
    pika, conn = _pika_connection()
    if not conn:
        _logger.error("[Kassa QR] Cannot publish wallet_lease_request — no RabbitMQ connection")
        return

    exchange = os.environ.get("RABBIT_EXCHANGE", "kassa.exchange")
    try:
        channel = conn.channel()
        channel.basic_publish(
            exchange=exchange,
            routing_key="kassa.to.crm.wallet_lease_request",
            body=_build_wallet_lease_request_xml(identity_uuid).encode("utf-8"),
            properties=pika.BasicProperties(content_type="application/xml", delivery_mode=2),
        )
        _logger.info("[Kassa QR] wallet_lease_request published for %s", identity_uuid)
    except Exception as exc:
        _logger.error("[Kassa QR] Failed to publish wallet_lease_request: %s", exc)
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ── Odoo helpers ──────────────────────────────────────────────────────────────

def _ensure_session_product(env, session_title: str) -> None:
    """Find or create a POS-available session product via Odoo ORM (idempotent)."""
    if env["product.template"].search(
        [("name", "=", session_title), ("available_in_pos", "=", True)], limit=1
    ):
        return

    categ = env["pos.category"].search([("name", "=", "Sessions")], limit=1)
    vals = {
        "name": session_title,
        "type": "consu",
        "list_price": 0.0,
        "available_in_pos": True,
    }
    if categ:
        vals["pos_categ_ids"] = [(6, 0, [categ.id])]

    env["product.template"].create(vals)
    _logger.info("[Kassa QR] Created session product: '%s'", session_title)


# ── Controller ────────────────────────────────────────────────────────────────

class KassaQrController(http.Controller):

    @http.route("/kassa/qr_scan", type="json", auth="user", methods=["POST"], csrf=False,
                groups="point_of_sale.group_pos_user")
    def qr_scan(self, identity_uuid=None, email=None, **kwargs):
        if not identity_uuid:
            return {"status": "error", "message": "identity_uuid is vereist."}

        env = request.env

        # 1. Find or create partner.
        partner = env["res.partner"].search([("x_user_id", "=", identity_uuid)], limit=1)
        created = False
        if not partner:
            name = f"QR Bezoeker ({email})" if email else f"QR Bezoeker ({identity_uuid[:8]})"
            vals = {"name": name, "x_user_id": identity_uuid, "customer_rank": 1}
            if email:
                vals["email"] = email
            partner = env["res.partner"].create(vals)
            created = True
            _logger.info(
                "[Kassa QR] Created placeholder partner %s for uuid %s",
                partner.id, identity_uuid,
            )
        elif email and not partner.email:
            partner.write({"email": email})

        # 2. Ask Planning for all sessions this visitor is registered for.
        sessions = _fetch_sessions_from_planning(identity_uuid)

        if sessions:
            titles_json = json.dumps([s["title"] for s in sessions])
            if partner.x_session_title != titles_json:
                partner.write({"x_session_title": titles_json})
            for s in sessions:
                _ensure_session_product(env, s["title"])
        else:
            # Fall back to whatever was stored from prior new_registration messages.
            raw = partner.x_session_title or ""
            if raw:
                try:
                    stored = json.loads(raw)
                    sessions = (
                        [{"session_id": "", "title": t} for t in stored]
                        if isinstance(stored, list)
                        else [{"session_id": "", "title": raw}]
                    )
                except (json.JSONDecodeError, ValueError):
                    sessions = [{"session_id": "", "title": raw}]
            if not sessions:
                _logger.info(
                    "[Kassa QR] No sessions found from Planning for %s; "
                    "no stored session titles either.",
                    identity_uuid,
                )

        # 3. Wallet lease: only publish if not already active.
        if partner.x_lease_active:
            return {
                "status": "already_active",
                "partner_id": partner.id,
                "partner_name": partner.name,
                "sessions": sessions,
            }

        _publish_lease_request(identity_uuid)

        status = "not_found_and_created" if created else "lease_requested"
        return {
            "status": status,
            "partner_id": partner.id,
            "partner_name": partner.name,
            "sessions": sessions,
        }
