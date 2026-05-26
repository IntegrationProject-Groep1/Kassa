# -*- coding: utf-8 -*-
"""
controllers/main.py — HTTP and RabbitMQ entry points for the Kassa POS QR-scan flow.

This module has two responsibilities:

1. **QR scan endpoint** (``/kassa/qr_scan``, JSON-RPC):
   Called by the POS frontend (qr_scanner.js) when the cashier scans a visitor's
   QR code.  The endpoint:
   - Finds or creates the Odoo partner for the scanned identity_uuid.
   - Calls the Frontend via RabbitMQ RPC (user_sessions_request) to get the
     visitor's registered sessions and syncs them to the partner record.
   - Publishes a wallet_lease_request to CRM so the visitor's wallet balance is
     transferred to Kassa authority for the duration of the event.
   - Returns partner data and session list to the POS screen.

2. **Service-worker override** (``/web/service-worker.js``):
   Replaces Odoo's default service worker with a cache-clearing no-op.
   Odoo's default SW caches 303 redirects which cause persistent login loops —
   this override prevents that without requiring a custom Odoo module.

XML builders in this file duplicate a subset of sender.py's builder functions.
This is intentional: the Odoo addon runs inside the Odoo server process, which
does not have access to the integration service's Python modules.  Both sets of
builders produce identical XML per the contract v2.3 schema.
"""
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

# Seconds to wait for Frontend's user_sessions_response before giving up.
_PLANNING_RPC_TIMEOUT = float(os.environ.get("PLANNING_RPC_TIMEOUT", "5"))


# ── XML builders ──────────────────────────────────────────────────────────────

def _now_utc() -> str:
    """Return the current UTC time as an ISO-8601 string (``YYYY-MM-DDTHH:MM:SSZ``)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_wallet_lease_request_xml(identity_uuid: str) -> str:
    """Build a contract-compliant ``wallet_lease_request`` XML message.

    Mirrors ``sender.build_wallet_lease_request_xml`` from the integration service.
    Duplicated here because the Odoo addon runs inside the Odoo process and cannot
    import from the external ``integratie/`` package.
    """
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
    """Build a contract-compliant ``user_sessions_request`` XML message.

    ``correlation_id`` is set to a fresh UUID per call so ``_fetch_sessions_from_frontend``
    can match the reply queue response back to this specific request even when
    multiple QR scans happen concurrently on different POS terminals.

    Mirrors ``sender.build_user_sessions_request_xml`` from the integration service.
    """
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


def _fetch_sessions_from_frontend(identity_uuid: str) -> List[Dict]:
    """
    RPC call to Frontend via RabbitMQ.
    Publishes user_sessions_request on kassa.exchange and waits up to
    PLANNING_RPC_TIMEOUT seconds for user_sessions_response on an exclusive
    reply queue.
    Returns list of {'session_id': ..., 'title': ..., 'price': ...} dicts,
    or [] on timeout/error.
    """
    pika, conn = _pika_connection()
    if not conn:
        return []

    corr_id = str(uuid.uuid4())
    xml_body = _build_user_sessions_request_xml(identity_uuid, corr_id)
    exchange = os.environ.get("RABBIT_EXCHANGE", "kassa.exchange")
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
                        price_el = session.find("price")
                        price: float | None = None
                        if price_el is not None and price_el.text:
                            try:
                                price = float(price_el.text.strip())
                            except ValueError:
                                pass
                        if title:
                            result.append({"session_id": sid, "title": title, "price": price})
            except Exception as exc:
                _logger.warning("[Kassa QR] Could not parse user_sessions_response: %s", exc)

        channel.basic_consume(queue=reply_queue, on_message_callback=_on_response, auto_ack=True)
        channel.basic_publish(
            exchange=exchange,
            routing_key="kassa.to.frontend.user_sessions_request",
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
            "[Kassa QR] Frontend RPC: %d session(s) returned for %s",
            len(result), identity_uuid,
        )
    except Exception as exc:
        _logger.warning("[Kassa QR] Frontend RPC error: %s", exc)
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

def _ensure_session_products(env, sessions: List[Dict]) -> None:
    """Find or create POS-available session products and keep their price in sync.

    sessions: list of {"title": str, "price": float|None}

    - Creates products that don't exist yet.
    - Updates list_price on existing products when Planning provides a new price,
      so cashiers clicking the tile directly see the correct price.
    - Idempotent — safe to call on every QR scan.
    """
    if not sessions:
        return

    titles = [s["title"] for s in sessions if s.get("title")]
    price_by_title: Dict[str, float | None] = {
        s["title"]: s.get("price") for s in sessions if s.get("title")
    }

    if not titles:
        return

    existing = env["product.template"].sudo().search([
        ("name", "in", titles),
        ("available_in_pos", "=", True),
    ])
    existing_by_name = {tmpl.name: tmpl for tmpl in existing}

    # Sync price on existing products when Planning provided a value.
    for title, price in price_by_title.items():
        if title in existing_by_name and price is not None:
            tmpl = existing_by_name[title]
            if round(float(tmpl.list_price or 0), 2) != round(float(price), 2):
                tmpl.write({"list_price": float(price)})
                _logger.info("[Kassa QR] Prijs bijgewerkt '%s': %.2f", title, price)

    titles_to_create = [t for t in titles if t not in existing_by_name]
    if not titles_to_create:
        return

    categ = env["pos.category"].sudo().search([("name", "=", "Sessions")], limit=1)
    for title in titles_to_create:
        price = price_by_title.get(title)
        vals: Dict = {
            "name": title,
            "type": "consu",
            "list_price": float(price) if price is not None else 0.0,
            "available_in_pos": True,
        }
        if categ:
            vals["pos_categ_ids"] = [(6, 0, [categ.id])]
        env["product.template"].sudo().create(vals)
        _logger.info("[Kassa QR] Sessieproduct aangemaakt: '%s' @ %.2f", title, price or 0.0)


# ── Controller ────────────────────────────────────────────────────────────────

class KassaQrController(http.Controller):
    """HTTP controller providing the QR-scan JSON endpoint and a service-worker override.

    All routes are registered under the Odoo HTTP layer and require an active
    user session (``auth='user'``) except the service-worker route which serves
    anonymous requests (``auth='none'``).
    """

    @http.route("/kassa/load_session_products", type="json", auth="user", methods=["POST"],
                csrf=False, groups="point_of_sale.group_pos_user")
    def load_session_products(self, titles=None, sessions=None, **kwargs):
        """Ensure session products exist in Odoo and return them for direct POS db insertion.

        Accepts either:
          sessions: [{"title": str, "price": float|None}, ...]  — preferred, syncs prices
          titles:   [str, ...]  — legacy, no price update

        Creates missing products (idempotent), syncs list_price from Planning, and
        returns them with the full POS loader field set so the caller can pass them
        to _loadProductProduct() to create proper Product instances in this.db.
        """
        env = request.env
        if sessions:
            _ensure_session_products(env, sessions)
            effective_titles = [s["title"] for s in sessions if s.get("title")]
        elif titles:
            _ensure_session_products(env, [{"title": t, "price": None} for t in titles])
            effective_titles = titles
        else:
            return {"products": []}

        # Use the same fields as _loader_params_product_product for compatibility
        # with PosStore._loadProductProduct().
        fields = []
        try:
            open_session = env["pos.session"].sudo().search(
                [("state", "in", ("opened", "opening_control"))], limit=1
            )
            if open_session:
                params = open_session._loader_params_product_product()
                fields = params.get("search_params", {}).get("fields", [])
        except Exception as exc:
            _logger.warning("[Kassa] Could not fetch product loader fields: %s", exc)

        if not fields:
            fields = [
                "id", "name", "display_name", "type", "lst_price", "standard_price",
                "uom_id", "uom_po_id", "taxes_id", "supplier_taxes_id", "pos_categ_ids",
                "available_in_pos", "tracking", "active", "write_date", "to_weight",
                "description_sale", "barcode", "default_code", "product_tmpl_id", "sale_ok",
                "categ_id", "image_128",
            ]

        products = env["product.product"].sudo().search_read(
            [("name", "in", effective_titles), ("available_in_pos", "=", True)],
            fields,
        )
        _logger.info(
            "[Kassa] load_session_products: %d product(en) teruggegeven voor %s",
            len(products), effective_titles,
        )
        return {"products": products}

    @http.route('/web/service-worker.js', type='http', auth='none', csrf=False)
    def service_worker(self, **kwargs):
        # Replace Odoo's default service worker with a no-op that clears all
        # existing caches on activation. The default SW caches 303 redirects
        # from /web → /web/login whenever a session is invalidated, causing
        # persistent login loops that survive hard refreshes.
        js = (
            "self.addEventListener('install', () => self.skipWaiting());\n"
            "self.addEventListener('activate', event => {\n"
            "  event.waitUntil(\n"
            "    caches.keys()\n"
            "      .then(keys => Promise.all(keys.map(k => caches.delete(k))))\n"
            "      .then(() => self.clients.claim())\n"
            "  );\n"
            "});\n"
        )
        return request.make_response(
            js,
            headers=[
                ('Content-Type', 'application/javascript'),
                ('Cache-Control', 'no-cache, no-store, must-revalidate'),
                ('Pragma', 'no-cache'),
                ('Expires', '0'),
            ],
        )

    @http.route("/kassa/qr_scan", type="json", auth="user", methods=["POST"], csrf=False,
                groups="point_of_sale.group_pos_user")
    def qr_scan(self, identity_uuid=None, email=None, **kwargs):
        """Process a QR-code scan from the POS frontend and return partner + session data.

        Called by ``qr_scanner.js`` in the browser after the camera decodes a QR code.
        The QR payload is either a plain UUID string or a JSON object
        ``{"identity_uuid": "...", "email": "..."}`` — both forms are handled by the
        JS layer before calling this endpoint.

        Processing steps
        ────────────────
        1. **Partner resolution** — find the Odoo partner by ``x_user_id``.
           If not found, try matching by email (links UUID to an existing record).
           If still not found, create a minimal placeholder partner so the POS can
           proceed immediately; the full profile arrives via ``new_registration`` later.

        2. **Session sync** — call the Frontend via RabbitMQ RPC
           (``user_sessions_request``) to get the visitor's registered sessions.
           Writes ``x_session_title`` and ``x_outstanding_amount`` to the partner and
           publishes a POS bus event so any open POS terminal sees the update.
           Falls back to the stored ``x_session_title`` if the Frontend is unreachable.

        3. **Wallet lease** — if the partner does not already have an active lease,
           publish ``wallet_lease_request`` to CRM and set ``x_lease_active=True``
           on the partner.  The lease is considered "requested" until CRM responds
           with ``wallet_lease_grant`` (handled by receiver.py).

        Returns a JSON dict with:
            ``status``       — "lease_requested" | "already_active" | "not_found_and_created" | "error"
            ``partner_id``   — Odoo ID of the resolved/created partner
            ``partner_name`` — Display name
            ``sessions``     — List of ``{"session_id": ..., "title": ..., "price": ...}`` dicts

        Access is restricted to users in the ``point_of_sale.group_pos_user`` group
        (i.e. active cashiers) — anonymous callers receive a 403.
        """
        if not identity_uuid:
            return {"status": "error", "message": "identity_uuid is vereist."}

        env = request.env

        # 1. Find or create partner.
        partner = env["res.partner"].sudo().search([("x_user_id", "=", identity_uuid)], limit=1)
        created = False
        if not partner and email:
            # Reverse lookup: UUID unknown but email matches an existing partner.
            partner = env["res.partner"].sudo().search([("email", "=", email)], limit=1)
            if partner:
                partner.sudo().write({"x_user_id": identity_uuid})
                _logger.info(
                    "[Kassa QR] Linked uuid %s to existing partner %s via email",
                    identity_uuid, partner.id,
                )
        if not partner:
            name = email if email else f"QR Bezoeker ({identity_uuid[:8]})"
            vals = {"name": name, "x_user_id": identity_uuid, "customer_rank": 1}
            if email:
                vals["email"] = email
            partner = env["res.partner"].sudo().create(vals)
            created = True
            _logger.info(
                "[Kassa QR] Created placeholder partner %s for uuid %s",
                partner.id, identity_uuid,
            )
        elif email and not partner.email:
            partner.sudo().write({"email": email})

        # 2. Ask Frontend for all sessions this visitor is registered for.
        sessions = _fetch_sessions_from_frontend(identity_uuid)

        if sessions:
            titles_json = json.dumps([
                {"session_id": s.get("session_id", ""), "title": s["title"], "price": s.get("price")}
                for s in sessions
            ])

            # Compute total outstanding from session prices when Planning provides them.
            # Uses cent-based math to avoid floating-point drift across multiple sessions.
            prices = [s["price"] for s in sessions if s.get("price") is not None]
            total_from_planning = (
                round(sum(round(p * 100) for p in prices) / 100, 2)
                if prices else None
            )

            write_vals: Dict = {}
            if partner.x_session_title != titles_json:
                write_vals["x_session_title"] = titles_json
            if total_from_planning is not None:
                write_vals["x_outstanding_amount"] = total_from_planning
                write_vals["x_payment_status"] = "unpaid"

            if write_vals:
                partner.write(write_vals)
                # Notify any POS terminal that has this partner selected.
                try:
                    env["pos.order"].send_partner_bus_event(
                        partner.id,
                        float(partner.x_outstanding_amount or 0.0),
                        partner.x_payment_status or "unpaid",
                        partner.name or "",
                    )
                    _logger.info("[Kassa QR] Bus event published for partner %s after Planning update", partner.id)
                except Exception as exc:
                    _logger.warning("[Kassa QR] Could not publish bus event: %s", exc)

            _ensure_session_products(env, sessions)
            try:
                env["pos.session"].sudo().kassa_notify_product_update()
            except Exception as exc:
                _logger.warning("[Kassa QR] Could not sync session products to POS: %s", exc)
        else:
            # Fall back to whatever was stored from prior new_registration messages.
            raw = partner.x_session_title or ""
            if raw:
                try:
                    stored = json.loads(raw)
                    if isinstance(stored, list):
                        sessions = [
                            s if isinstance(s, dict) else {"session_id": "", "title": s, "price": None}
                            for s in stored
                        ]
                    else:
                        sessions = [{"session_id": "", "title": raw, "price": None}]
                except (json.JSONDecodeError, ValueError):
                    sessions = [{"session_id": "", "title": raw, "price": None}]
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

        # Mark lease as requested so the POS wallet notification appears immediately.
        # x_lease_id stays "" until CRM confirms; Badge Wallet payment is blocked until then.
        partner.write({
            "x_lease_active": True,
            "x_lease_id": "",
            "x_lease_transaction_count": 0,
        })

        # Notify any open POS terminal so the "Wallet wordt geactiveerd..." indicator
        # shows up immediately without waiting for a product/session bus event.
        try:
            env["pos.order"].send_partner_bus_event(
                partner.id,
                float(partner.x_outstanding_amount or 0.0),
                partner.x_payment_status or "pending",
                partner.name or "",
            )
        except Exception as exc:
            _logger.warning("[Kassa QR] Could not publish post-lease bus event: %s", exc)

        status = "not_found_and_created" if created else "lease_requested"
        return {
            "status": status,
            "partner_id": partner.id,
            "partner_name": partner.name,
            "sessions": sessions,
        }
