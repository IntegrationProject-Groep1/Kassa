"""
receiver.py — RabbitMQ consumer for the Kassa integration service.

Connects to the broker defined by RABBIT_HOST/PORT/VHOST and listens on the
queue set by RABBIT_INCOMING_QUEUE (default: kassa.incoming).

Handles seven incoming message types sent by the CRM / IoT teams:
    - new_registration     → creates or updates a res.partner in Odoo
    - profile_update       → updates name, email, age, VAT on an existing partner
    - badge_scanned        → looks up a customer by x_badge_id; drives the
                             wallet lease lifecycle on check_in / check_out
    - cancel_registration  → sets active=False on the partner (soft delete)
    - wallet_lease_grant   → CRM confirms balance authority; reconciles wallet
                             balance and stores the lease_id on the partner
    - wallet_remote_topup  → CRM pushes an online top-up to the active lease;
                             updates balance and broadcasts wallet_balance_update
    - event_ended          → festival ended; returns all active leases to CRM

Error handling:
    - Unparseable XML          → basic_nack(requeue=False) + system_error sent
    - XSD validation failure   → basic_nack(requeue=False) + system_error sent
    - Unknown message type     → basic_nack(requeue=False) + system_error sent
    - Odoo connection/API error → retry up to 3 times via RETRY_QUEUE, then DLQ
    - Duplicate message_id     → basic_ack, no Odoo write (silently ignored)

Duplicate detection uses an in-memory bounded cache (max 10,000 entries)
with FIFO eviction.
"""

import json
import os
import logging
import pika
import xmlrpc.client  # nosec
import defusedxml.xmlrpc
import defusedxml.ElementTree as ET
from xml.etree.ElementTree import Element
from collections import OrderedDict
from typing import Any, List, Dict, Optional, Tuple, cast
from lxml import etree

from config_utils import get_env, parse_rabbit_port, require_env, parse_xml_float
from sender import (
    send_error_to_queue, flush_buffer, now_utc, setup_exchange, EXCHANGE_NAME,
    send_typed_message,
    build_wallet_lease_request_xml, build_wallet_lease_return_xml,
    build_wallet_balance_update_xml, build_user_sessions_request_xml,
)
from monitoring import monitor
from typing_utils import OdooModelsProxy, OdooRecord

defusedxml.xmlrpc.monkey_patch()


logger = logging.getLogger(__name__)


# ── Environment ────────────────────────────────────────────────────────────────
_rabbit_env = require_env("RABBIT_HOST", "RABBIT_USER", "RABBIT_PASS")
RABBIT_HOST = _rabbit_env["RABBIT_HOST"]
RABBIT_USER = _rabbit_env["RABBIT_USER"]
RABBIT_PASS = _rabbit_env["RABBIT_PASS"]

RABBIT_PORT = parse_rabbit_port()
RABBIT_VHOST = os.environ.get("RABBIT_VHOST", "/")

_odoo_env = require_env("ODOO_URL", "ODOO_DB", "ODOO_USER", "ODOO_PASS")
ODOO_URL = _odoo_env["ODOO_URL"]
ODOO_DB = _odoo_env["ODOO_DB"]
ODOO_USER = _odoo_env["ODOO_USER"]
ODOO_PASS = _odoo_env["ODOO_PASS"]

QUEUE_NAME = get_env("RABBIT_INCOMING_QUEUE", "kassa.incoming")
FRONTEND_EXCHANGE = os.environ.get("RABBIT_FRONTEND_EXCHANGE", "frontend.exchange")
DLX_NAME = get_env("RABBIT_DLX", EXCHANGE_NAME)
DLQ_NAME = get_env("RABBIT_DLQ", "kassa.incoming.dlq")
DLQ_ROUTING_KEY = get_env("RABBIT_DLX_ROUTING_KEY", DLQ_NAME)

RETRY_QUEUE = f"{QUEUE_NAME}.retry"
RETRY_DELAY_MS = 5000  # 5 seconds
MAX_RETRIES = 3

# ── XSD schema mapping ─────────────────────────────────────────────────────────
SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "schemas")

SCHEMA_MAP = {
    "new_registration": os.path.join(SCHEMA_DIR, "schema_new_registration.xsd"),
    "profile_update": os.path.join(SCHEMA_DIR, "schema_profile_update.xsd"),
    "badge_scanned": os.path.join(SCHEMA_DIR, "schema_badge_scanned.xsd"),
    "cancel_registration": os.path.join(SCHEMA_DIR, "schema_cancel_registration.xsd"),
    "user_event": os.path.join(SCHEMA_DIR, "schema_user_event.xsd"),
    "wallet_lease_grant": os.path.join(SCHEMA_DIR, "schema_wallet_lease_grant.xsd"),
    "wallet_remote_topup": os.path.join(SCHEMA_DIR, "schema_wallet_remote_topup.xsd"),
    "event_ended": os.path.join(SCHEMA_DIR, "schema_event_ended.xsd"),
    "user_registered":        os.path.join(SCHEMA_DIR, "schema_user_registered.xsd"),
    "user_unregistered":      os.path.join(SCHEMA_DIR, "schema_user_unregistered.xsd"),
    "user_sessions_response": os.path.join(SCHEMA_DIR, "schema_user_sessions_response.xsd"),
    "session_created":        os.path.join(SCHEMA_DIR, "schema_session_created.xsd"),
    "session_updated":        os.path.join(SCHEMA_DIR, "schema_session_updated.xsd"),
    "session_deleted":        os.path.join(SCHEMA_DIR, "schema_session_deleted.xsd"),
}

_schema_cache: dict[str, etree.XMLSchema] = {}


# ── Idempotency cache ──────────────────────────────────────────────────────────
MAX_CACHE_SIZE = 10_000
seen_message_ids: OrderedDict = OrderedDict()


def _remember_message_id(message_id: str) -> None:
    seen_message_ids[message_id] = now_utc()
    if len(seen_message_ids) > MAX_CACHE_SIZE:
        seen_message_ids.popitem(last=False)


def is_duplicate(message_id: str, track_if_new: bool = True) -> bool:
    """Return True if this message_id has already been processed in this session."""
    if message_id in seen_message_ids:
        logger.info("[IDEMPOTENCY] Duplicate detected: message_id=%s – skipped", message_id)
        return True
    if track_if_new:
        _remember_message_id(message_id)
    return False


# ── Odoo connection ────────────────────────────────────────────────────────────
def get_odoo_connection() -> Tuple[int, OdooModelsProxy]:
    """Open an XML-RPC session with Odoo and return (uid, models proxy)."""
    required = require_env("ODOO_URL", "ODOO_DB", "ODOO_USER", "ODOO_PASS")
    common = xmlrpc.client.ServerProxy(f"{required['ODOO_URL']}/xmlrpc/2/common")
    uid = common.authenticate(
        required["ODOO_DB"], required["ODOO_USER"], required["ODOO_PASS"], {}
    )
    if not isinstance(uid, int) or uid <= 0:
        raise ConnectionError(
            "Odoo authentication failed. Check ODOO_USER/ODOO_PASS and ODOO_DB."
        )
    models = xmlrpc.client.ServerProxy(f"{required['ODOO_URL']}/xmlrpc/2/object")
    return uid, cast(OdooModelsProxy, models)


# ── XSD validation ─────────────────────────────────────────────────────────────
def validate_xml(xml_text: str, msg_type: str) -> None:
    """Validate xml_text against the XSD schema for msg_type."""
    schema_path = SCHEMA_MAP.get(msg_type)
    if not schema_path or not os.path.exists(schema_path):
        logger.warning("[VALIDATION] No XSD schema found for type '%s' – skipping validation", msg_type)
        return

    if msg_type not in _schema_cache:
        schema_doc = etree.parse(schema_path)
        _schema_cache[msg_type] = etree.XMLSchema(schema_doc)

    xml_doc = etree.fromstring(xml_text.encode("utf-8"))

    if not _schema_cache[msg_type].validate(xml_doc):
        errors = str(_schema_cache[msg_type].error_log)
        raise ValueError(f"XSD validation failed for '{msg_type}':\n{errors}")

    logger.info("[VALIDATION] ✓ XSD validation passed for type '%s'", msg_type)


# ── Bus event publisher ────────────────────────────────────────────────────────

def _publish_partner_bus_event(
    uid: int, models, partner_id: int,
    outstanding_amount: float, payment_status: str, name: str,
) -> None:
    """Publish a kassa_partner_update bus event so the POS frontend updates immediately.

    The POS JS subscribes to the kassa_partner_update channel and on receipt
    fetches the full partner record (including all Kassa custom fields) and
    upserts it into the local partner list — covering both updates to existing
    partners and brand-new partners appearing mid-session.

    Non-fatal: partner data is already persisted in Odoo before this is called.
    """
    try:
        models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "pos.order", "send_partner_bus_event",
            [partner_id, outstanding_amount, payment_status, name],
        )
        logger.info("[BUS] ✓ Published partner update: partner_id=%s", partner_id)
    except Exception as e:
        logger.warning("[BUS] Could not publish bus event for partner_id=%s: %s", partner_id, e)
        monitor.log("warning", "system_error",
                    f"POS bus event failed for partner {partner_id}: {str(e)[:300]}")


# ── Business logic per message type ───────────────────────────────────────────

def _ensure_session_product(
    uid: int, models: OdooModelsProxy, session_title: str,
    price: float | None = None, session_id: str | None = None,
) -> None:
    """Find or create a POS-available product for the given session (idempotent).

    Looks up by x_session_id first when provided — this correctly handles title
    renames without creating a duplicate product. Falls back to name lookup for
    products created before x_session_id was introduced.
    If *price* is provided it is always written to list_price.
    """
    existing = None
    found_by_session_id = False

    # Primary lookup: by x_session_id (survives title renames)
    if session_id:
        existing = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "product.template", "search_read",
            [[["x_session_id", "=", session_id], ["available_in_pos", "=", True]]],
            {"fields": ["id", "name", "list_price", "x_session_id"], "limit": 1},
        )
        if existing:
            found_by_session_id = True

    # Fallback: by name (backwards compat for pre-existing products without x_session_id)
    if not existing:
        existing = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "product.template", "search_read",
            [[["name", "=", session_title], ["available_in_pos", "=", True]]],
            {"fields": ["id", "list_price", "x_session_id"], "limit": 1},
        )

    if existing:
        product_id = existing[0]["id"]
        write_vals: Dict[str, Any] = {}
        # Only check for a title rename when found by x_session_id — if we found it
        # by name the name already matches by definition.
        if found_by_session_id and existing[0].get("name") != session_title:
            write_vals["name"] = session_title
        if price is not None and existing[0].get("list_price") != price:
            write_vals["list_price"] = price
        # Backfill x_session_id on products created before this field existed
        if session_id and not existing[0].get("x_session_id"):
            write_vals["x_session_id"] = session_id
        if write_vals:
            models.execute_kw(
                ODOO_DB, uid, ODOO_PASS,
                "product.template", "write",
                [[product_id], write_vals],
            )
            logger.info("[SESSION_PRODUCT] ✓ Updated product id=%s: %s", product_id, write_vals)
        else:
            logger.debug("[SESSION_PRODUCT] Already up to date: '%s'", session_title)
        return

    # Look up the Sessions POS category created by odoo_setup.
    categ = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "pos.category", "search_read",
        [[["name", "=", "Sessions"]]],
        {"fields": ["id"], "limit": 1},
    )
    categ_id = categ[0]["id"] if categ else False

    vals: Dict[str, Any] = {
        "name": session_title,
        "type": "consu",
        "list_price": price if price is not None else 0.0,
        "available_in_pos": True,
    }
    if session_id:
        vals["x_session_id"] = session_id
    if categ_id:
        vals["pos_categ_ids"] = [(6, 0, [categ_id])]

    models.execute_kw(ODOO_DB, uid, ODOO_PASS, "product.template", "create", [vals])
    logger.info(
        "[SESSION_PRODUCT] ✓ Created POS product: '%s' | price=%.2f",
        session_title, price if price is not None else 0.0,
    )


def process_new_registration(root: Element, uid: int, models: OdooModelsProxy) -> None:
    """Create or update the Odoo partner for a newly registered attendee (Flow 1).

    Upsert strategy:
    1. Search res.partner by x_user_id (identity_uuid) — the only lookup key.
    2. If not found, create a new res.partner record.

    No email fallback: new_registration always contains an identity_uuid (enforced
    by XSD), so a UUID-only lookup is sufficient and unambiguous.

    company vs. private: the <type> field drives is_company; company partners also
    receive the VAT number (required by CRM per §11.1).
    """
    body = root.find("body")
    if body is None:
        raise ValueError("new_registration: <body> missing")

    customer = body.find("customer")
    if customer is None:
        raise ValueError("new_registration: <customer> missing in <body>")

    identity_uuid = (customer.findtext("identity_uuid") or "").strip()
    email = (customer.findtext("email") or "").strip()

    contact = customer.find("contact")
    first_name = (contact.findtext("first_name") or "").strip() if contact is not None else ""
    last_name = (contact.findtext("last_name") or "").strip() if contact is not None else ""
    contact_name = " ".join(part for part in [first_name, last_name] if part).strip()

    # Fallback for old 'name' tag if present, but priority to first+last name
    name = contact_name or (customer.findtext("name") or "").strip()

    company_name = (customer.findtext("company_name") or "").strip()
    ctype = (customer.findtext("type") or "private").strip().lower()
    vat_number = (customer.findtext("vat_number") or "").strip()
    dob_str = (customer.findtext("date_of_birth") or "").strip()
    badge_id = (customer.findtext("badge_id") or "").strip()
    session_title = (customer.findtext("session_title") or "").strip()

    payment_due_el = customer.find("payment_due")
    if payment_due_el is None:
        # Compatibility fallback if payment_due was moved to body by normalization
        payment_due_el = body.find("payment_due")

    if payment_due_el is None:
        raise ValueError("new_registration: <payment_due> missing in <customer>")

    status = (payment_due_el.findtext("status") or "unpaid").strip()
    amount = parse_xml_float(payment_due_el.find("amount"))

    if not identity_uuid:
        raise ValueError("new_registration: identity_uuid missing in <customer>")

    # Contract Section 11.1: VAT number required for companies
    if ctype == "company" and not vat_number:
        raise ValueError(
            "new_registration: vat_number is mandatory for company type per contract Section 11.1"
        )

    existing: List[OdooRecord] = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "res.partner", "search_read",
        [[["x_user_id", "=", identity_uuid]]],
        {"fields": ["id", "name", "x_user_id", "x_session_title"], "limit": 1},
    )

    # Mapping note: `x_user_id` stores the canonical user identifier.
    # The system-wide canonical ID is `master_uuid` from the Identity Service.
    # Incoming `new_registration` messages MUST contain `user_id` equal to
    # the Identity `master_uuid` so that all teams (CRM/Kassa/Frontend)
    # reference the same UID. Do NOT generate local UUIDs as a fallback.
    partner_vals: Dict[str, Any] = {
        "name": name or company_name or "Unknown",
        "email": email,
        "x_user_id": identity_uuid,
        "is_company": ctype == "company",
        "x_payment_status": status,
        "x_outstanding_amount": amount,
        # Required so Odoo POS includes this partner in the customer tab.
        # The POS session loader and the partner-list search both filter by
        # customer_rank > 0; without this, the partner is invisible in the UI.
        "customer_rank": 1,
    }
    if session_title:
        existing_raw = existing[0].get("x_session_title") or "" if existing else ""
        try:
            existing_titles = json.loads(existing_raw) if existing_raw else []
            if not isinstance(existing_titles, list):
                existing_titles = [existing_titles]
        except (json.JSONDecodeError, ValueError):
            existing_titles = [existing_raw] if existing_raw else []
        if session_title not in existing_titles:
            existing_titles.append(session_title)
        partner_vals["x_session_title"] = json.dumps(existing_titles)
    if badge_id:
        partner_vals["x_badge_id"] = badge_id
    if dob_str:
        partner_vals["x_date_of_birth"] = dob_str
    if vat_number:
        partner_vals["vat"] = vat_number

    if existing:
        partner_id = existing[0]["id"]
        models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "res.partner", "write",
            [[partner_id], partner_vals],
        )
        logger.info("[NEW_REGISTRATION] ✓ Customer updated: Odoo ID=%s", partner_id)
    else:
        partner_id = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "res.partner", "create",
            [partner_vals],
        )
        logger.info("[NEW_REGISTRATION] ✓ New customer created: Odoo ID=%s", partner_id)

    logger.info("[NEW_REGISTRATION]   Payment due status: %s", status)
    monitor.log(
        "info", "registration",
        f"new_registration processed: Odoo ID={partner_id} | status={status}"
    )

    if session_title:
        _ensure_session_product(uid, models, session_title)

    _publish_partner_bus_event(
        uid, models, partner_id,
        amount, status, partner_vals["name"],
    )


def process_profile_update(root: Element, uid: int, models: OdooModelsProxy) -> None:
    """Apply a partial profile update from CRM to an existing Odoo partner (Flow 3).

    Only fields present in the XML payload are updated — absent elements are not
    overwritten with empty values. This is intentional: CRM sends profile_update
    only for the fields that changed, not the full partner record.

    x_session_title is stored as a JSON-encoded list because a partner may be
    registered for multiple sessions and Odoo custom fields do not support arrays.
    """
    body = root.find("body")
    if body is None:
        raise ValueError("profile_update: <body> missing")

    identity_uuid = (body.findtext("identity_uuid") or "").strip()
    email = (body.findtext("email") or "").strip()

    contact = body.find("contact")
    first_name = (contact.findtext("first_name") or "").strip() if contact is not None else ""
    last_name = (contact.findtext("last_name") or "").strip() if contact is not None else ""
    contact_name = " ".join(part for part in [first_name, last_name] if part).strip()

    # Fallback for old 'name' tag if present
    name = contact_name or (body.findtext("name") or "").strip()

    company_name = (body.findtext("company_name") or "").strip()
    ctype = (body.findtext("type") or "private").strip().lower()
    vat_number = (body.findtext("vat_number") or "").strip()
    dob_str = (body.findtext("date_of_birth") or "").strip()

    if not identity_uuid:
        raise ValueError("profile_update: identity_uuid missing in <body>")

    existing: List[OdooRecord] = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "res.partner", "search_read",
        [[["x_user_id", "=", identity_uuid]]],
        {"fields": ["id", "name"], "limit": 1},
    )

    update_vals: Dict[str, Any] = {
        "email": email,
        "is_company": ctype == "company",
        "name": name or company_name or "Unknown",
    }
    if body.find("vat_number") is not None:
        update_vals["vat"] = vat_number if vat_number else False
    if company_name and not name:
        update_vals["name"] = company_name
    if body.find("date_of_birth") is not None:
        update_vals["x_date_of_birth"] = dob_str if dob_str else False

    payment_due_el = body.find("payment_due")
    outstanding_amount: Optional[float] = None
    payment_status: Optional[str] = None
    if payment_due_el is not None:
        outstanding_amount = parse_xml_float(payment_due_el.find("amount"))
        payment_status = (payment_due_el.findtext("status") or "unpaid").strip()
        update_vals["x_outstanding_amount"] = outstanding_amount
        update_vals["x_payment_status"] = payment_status

    if existing:
        partner_id = existing[0]["id"]
        models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "res.partner", "write",
            [[partner_id], update_vals],
        )
        logger.info("[PROFILE_UPDATE] ✓ Profile updated: Odoo ID=%s", partner_id)
        monitor.log(
            "info", "registration",
            f"profile_update processed: Odoo ID={partner_id}"
        )
    else:
        update_vals["x_user_id"] = identity_uuid
        partner_id = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "res.partner", "create",
            [update_vals],
        )
        logger.warning("[PROFILE_UPDATE] ⚠ Customer not found – created new: Odoo ID=%s", partner_id)

    if outstanding_amount is not None and payment_status is not None:
        _publish_partner_bus_event(
            uid, models, partner_id,
            outstanding_amount, payment_status, update_vals.get("name", "Unknown"),
        )


def process_badge_scan(root: Element, uid: int, models: OdooModelsProxy) -> None:
    """Look up an attendee by badge/QR and trigger the wallet lease lifecycle (Flow 2).

    Two scan variants are accepted (XSD allows either, not both):
    - Physical badge: <body><badge_id>…</badge_id>  — looked up via x_badge_id
    - QR code:        <body><identity_uuid>…</identity_uuid> — looked up via x_user_id

    Location-driven behaviour:
    - entrance / bar / main_bar / session → start wallet lease if not already active
      (sends wallet_lease_request to CRM; CRM responds with wallet_lease_grant)
    - session → additionally sends user_sessions_request to Frontend so the POS screen
      can display the sessions the attendee is registered for
    - checkout → not in this function; lease return is triggered by event_ended

    If neither badge_id nor identity_uuid is in the body, a system_error is sent and
    the message is rejected. Requiring at least one identifier keeps the flow deterministic.
    """
    body = root.find("body")
    if body is None:
        raise ValueError("badge_scanned: <body> missing")

    badge_id = (body.findtext("badge_id") or "").strip()
    identity_uuid_scanned = (body.findtext("identity_uuid") or "").strip()
    location = (body.findtext("location") or "unknown").strip()
    scanned_at = (body.findtext("scanned_at") or "").strip()
    message_id = root.findtext("header/message_id")

    _partner_fields = ["id", "name", "x_user_id", "x_wallet_balance",
                       "x_date_of_birth", "is_company",
                       "x_lease_active", "x_lease_id", "x_lease_transaction_count"]

    if badge_id:
        existing: List[OdooRecord] = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "res.partner", "search_read",
            [[["x_badge_id", "=", badge_id]]],
            {"fields": _partner_fields, "limit": 1},
        )
        scan_label = f"badge({badge_id})"
        not_found_code = "badge_not_found"
        not_found_desc = f"Badge {badge_id} not found in local Odoo cache."
    elif identity_uuid_scanned:
        existing = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "res.partner", "search_read",
            [[["x_user_id", "=", identity_uuid_scanned]]],
            {"fields": _partner_fields, "limit": 1},
        )
        scan_label = f"qr_code({identity_uuid_scanned})"
        not_found_code = "profile_not_found"
        not_found_desc = f"identity_uuid {identity_uuid_scanned} not found in local Odoo cache."
    else:
        raise ValueError("badge_scanned: neither badge_id nor identity_uuid present in <body>")

    logger.info("[BADGE_SCANNED] Processing %s scan from %s at %s", scan_label, location, scanned_at)

    if not existing:
        logger.warning("[BADGE_SCANNED] ⚠ %s not found in local cache – sending system_error", scan_label)
        send_error_to_queue(
            error_code=not_found_code,
            related_message_id=message_id,
            error_description=not_found_desc,
        )
        return

    partner = existing[0]
    identity_uuid = partner.get("x_user_id") or ""

    logger.info(
        "[BADGE_SCANNED] ✓ Recognised: Odoo ID=%s | %s | Location=%s",
        partner["id"], scan_label, location,
    )

    if location in ("entrance", "bar", "main_bar", "session"):
        if not identity_uuid:
            logger.warning("[BADGE_SCANNED] check_in skipped: no identity_uuid for partner %s", partner["id"])
            send_error_to_queue(
                error_code="partner_not_linked",
                related_message_id=message_id,
                error_description=(
                    f"Partner (Odoo ID={partner['id']}) found via {scan_label} "
                    f"but has no x_user_id — cannot request wallet lease."
                ),
            )
            return
        if not partner.get("x_lease_active"):
            xml = build_wallet_lease_request_xml(
                identity_uuid=identity_uuid,
                badge_id=badge_id or None,
            )
            send_typed_message("wallet_lease_request", xml, record_id=partner["id"], model="res.partner")
            models.execute_kw(
                ODOO_DB, uid, ODOO_PASS,
                "res.partner", "write",
                [[partner["id"]], {"x_lease_active": True, "x_lease_id": "", "x_lease_transaction_count": 0}],
            )
            logger.info("[BADGE_SCANNED] ✅ Lease requested for %s", identity_uuid)
            monitor.log(
                "info", "badge",
                f"badge_scanned: wallet_lease_request sent | identity_uuid={identity_uuid}"
                f" | location={location}"
            )
        else:
            logger.info("[BADGE_SCANNED] check_in: lease already active for %s, skipping", identity_uuid)
        if location == "session":
            logger.info(
                "[USER_SESSIONS_REQUEST] Building request | identity_uuid=%s | correlation_id=%s",
                identity_uuid, message_id,
            )
            sessions_xml = build_user_sessions_request_xml(
                identity_uuid=identity_uuid,
                correlation_id=message_id,
            )
            logger.info(
                "[USER_SESSIONS_REQUEST] XSD validation + publish | routing_key=kassa.to.frontend.user_sessions_request"
            )
            send_typed_message("user_sessions_request", sessions_xml, exchange="kassa.exchange")
            logger.info(
                "[USER_SESSIONS_REQUEST] ✅ Sent to kassa.exchange | identity_uuid=%s | correlation_id=%s",
                identity_uuid, message_id,
            )
            monitor.log(
                "info", "session",
                f"user_sessions_request sent | identity_uuid={identity_uuid}"
                f" | correlation_id={message_id}"
            )
    else:
        logger.info("[BADGE_SCANNED] Location=%s: no lease action taken for %s", location, scan_label)


def _return_lease(partner_id: int, uid: int, models: OdooModelsProxy) -> None:
    """Clear Odoo lease state then notify CRM via wallet_lease_return.

    Always fetches fresh partner data right before acting so the final
    balance, lease_id, and tx_count in the message reflect true state
    regardless of how long ago the badge was scanned.

    Odoo is cleared before the message is published: if the send fails,
    Kassa remains consistent and CRM reconciles at event-end rather than
    receiving a duplicate return on the next check-out.
    """
    logger.info("[LEASE_RETURN] Initiating lease return for partner_id=%d", partner_id)
    fresh: List[OdooRecord] = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "res.partner", "search_read",
        [[["id", "=", partner_id]]],
        {"fields": ["id", "x_user_id", "x_wallet_balance",
                    "x_lease_id", "x_lease_transaction_count"], "limit": 1},
    )
    if not fresh:
        logger.warning("[LEASE_RETURN] Partner %s not found during lease return", partner_id)
        return

    partner = fresh[0]
    identity_uuid = partner.get("x_user_id") or ""
    final_balance = float(partner.get("x_wallet_balance") or 0.0)
    lease_id = partner.get("x_lease_id") or ""
    tx_count = int(partner.get("x_lease_transaction_count") or 0)

    models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "res.partner", "write",
        [[partner_id], {
            "x_lease_active": False,
            "x_lease_id": "",
            "x_lease_transaction_count": 0,
        }],
    )

    xml = build_wallet_lease_return_xml(
        identity_uuid=identity_uuid,
        final_balance=final_balance,
        lease_id=lease_id,
        transaction_count=tx_count,
    )
    send_typed_message("wallet_lease_return", xml, record_id=partner_id, model="res.partner")
    logger.info("[LEASE_RETURN] ✅ Lease returned for %s (balance=%.2f, tx=%d)", identity_uuid, final_balance, tx_count)
    monitor.log(
        "info", "wallet",
        f"Published wallet_lease_return | identity_uuid={identity_uuid} | "
        f"balance={final_balance:.2f} | tx={tx_count}"
    )


def process_wallet_lease_grant(root: Element, uid: int, models: OdooModelsProxy) -> None:
    """CRM confirms balance authority for a leased wallet (Flow 6A).

    When Kassa sends wallet_lease_request, CRM transfers the wallet balance to Kassa
    and responds with wallet_lease_grant. From this point until wallet_lease_return,
    Kassa is the source of truth for this partner's wallet balance.

    Pending-topup merge: if the attendee topped up their wallet online between the
    moment of badge scan and the moment CRM sends wallet_lease_grant, the top-up
    arrives as wallet_remote_topup before the grant is processed. Because there is no
    active lease yet at that point, the topup is buffered in x_pending_topup_balance.
    This function adds that buffer to the granted balance, then zeroes the buffer.
    Without this merge the attendee would see a lower balance than they paid for.
    """
    body = root.find("body")
    if body is None:
        raise ValueError("wallet_lease_grant: <body> missing")

    identity_uuid = (body.findtext("identity_uuid") or "").strip()
    lease_id = (body.findtext("lease_id") or "").strip()
    current_balance_text = (body.findtext("current_balance") or "0").strip()

    if not identity_uuid:
        raise ValueError("wallet_lease_grant: identity_uuid missing")

    try:
        current_balance = float(current_balance_text)
    except ValueError:
        raise ValueError(f"wallet_lease_grant: invalid current_balance '{current_balance_text}'")

    logger.info("[LEASE_GRANT] Received for identity_uuid=%s | balance=%.2f | lease_id=%s",
                identity_uuid, current_balance, lease_id or "<none>")

    amount_due: Optional[float] = None
    payment_due_el = body.find("payment_due")
    if payment_due_el is not None:
        amount_due = parse_xml_float(payment_due_el.find("amount"))

    existing: List[OdooRecord] = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "res.partner", "search_read",
        [[["x_user_id", "=", identity_uuid]]],
        {"fields": ["id", "name", "x_payment_status", "x_outstanding_amount",
                    "x_pending_topup_balance"], "limit": 1},
    )
    if not existing:
        logger.warning("[LEASE_GRANT] No partner found for identity_uuid=%s", identity_uuid)
        return

    partner = existing[0]

    # ── Apply any pending top-ups that arrived before the lease grant ──────────
    # If the cashier processed a top-up between the visitor's QR scan and this
    # lease grant, the amount was parked in x_pending_topup_balance instead of
    # being added to x_wallet_balance (which would have been overwritten here).
    # Now we know CRM's authoritative balance — merge and clear the pending field.
    pending_topup = float(partner.get("x_pending_topup_balance") or 0.0)
    final_balance = round(current_balance + pending_topup, 2)

    if pending_topup > 0:
        logger.info(
            "[LEASE_GRANT] Merging pending top-up €%.2f with CRM balance €%.2f → final €%.2f for %s",
            pending_topup, current_balance, final_balance, identity_uuid
        )

    write_vals: dict = {
        "x_wallet_balance": final_balance,
        "x_lease_id": lease_id,
        "x_lease_active": True,
        "x_pending_topup_balance": 0.0,  # cleared — merged into x_wallet_balance
    }
    if amount_due is not None:
        write_vals["x_outstanding_amount"] = amount_due

    models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "res.partner", "write",
        [[partner["id"]], write_vals],
    )
    logger.info(
        "[LEASE_GRANT] ✅ Lease granted for %s | balance=%.2f | payment_due=%s | lease_id=%s",
        identity_uuid, final_balance,
        f"€{amount_due:.2f}" if amount_due is not None else "not provided",
        lease_id,
    )

    # ── Notify external frontend of the authoritative balance ──────────────────
    # Now that the lease is granted and the balance is final (including any
    # pending top-ups), send wallet_balance_update so the frontend always shows
    # the correct balance regardless of when the top-up was processed.
    update_xml = build_wallet_balance_update_xml(
        identity_uuid=identity_uuid,
        new_balance=final_balance,
        authority="kassa",
        status="active",
    )
    send_typed_message("wallet_balance_update", update_xml)
    logger.info(
        "[LEASE_GRANT] ✅ wallet_balance_update sent to frontend for %s (balance=%.2f)",
        identity_uuid, final_balance
    )
    monitor.log(
        "info", "wallet",
        f"wallet_lease_grant processed | identity_uuid={identity_uuid} | balance={final_balance:.2f}"
    )

    # When payment_due is absent (Planning was available and CRM didn't send a total),
    # use the outstanding amount already stored on the partner (set by new_registration).
    # This ensures the bus event payload reflects the real DB state and the POS OWL
    # effect fires correctly on the refetch.
    effective_outstanding = (
        amount_due if amount_due is not None
        else float(partner.get("x_outstanding_amount") or 0.0)
    )
    _publish_partner_bus_event(
        uid, models, partner["id"],
        effective_outstanding,
        partner.get("x_payment_status") or "unpaid",
        partner.get("name") or "Unknown",
    )


def process_wallet_remote_topup(root: Element, uid: int, models: OdooModelsProxy) -> None:
    """Apply a remotely purchased top-up to the partner's wallet (Flow 6B).

    Two-path logic based on whether a lease is currently active:
    - Active lease (x_lease_active=True): add amount directly to x_wallet_balance
      and immediately send wallet_balance_update to Frontend so the POS screen reflects
      the new balance in real time.
    - No active lease: the attendee has topped up but has not yet scanned their badge.
      Buffer the amount in x_pending_topup_balance. When wallet_lease_grant arrives
      later, process_wallet_lease_grant() merges the buffer into the granted balance.

    This split prevents balance corruption: writing to x_wallet_balance before the
    lease is granted would make Kassa claim authority over a balance CRM still owns.
    """
    body = root.find("body")
    if body is None:
        raise ValueError("wallet_remote_topup: <body> missing")

    identity_uuid = (body.findtext("identity_uuid") or "").strip()
    add_amount_text = (body.findtext("add_amount") or "0").strip()
    reason = (body.findtext("reason") or "").strip()

    if not identity_uuid:
        raise ValueError("wallet_remote_topup: identity_uuid missing")

    try:
        add_amount = float(add_amount_text)
    except ValueError:
        raise ValueError(f"wallet_remote_topup: invalid add_amount '{add_amount_text}'")

    if add_amount <= 0:
        logger.warning(
            "[REMOTE_TOPUP] Non-positive add_amount=%.2f for %s — ignoring",
            add_amount, identity_uuid,
        )
        return

    logger.info("[REMOTE_TOPUP] Received for identity_uuid=%s | add_amount=%.2f | reason=%s",
                identity_uuid, add_amount, reason or "<none>")

    existing: List[OdooRecord] = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "res.partner", "search_read",
        [[["x_user_id", "=", identity_uuid]]],
        {"fields": ["id", "name", "x_lease_active", "x_lease_id",
                    "x_pending_topup_balance", "x_outstanding_amount",
                    "x_payment_status"], "limit": 1},
    )
    if not existing:
        logger.warning("[REMOTE_TOPUP] No partner found for identity_uuid=%s", identity_uuid)
        return

    partner = existing[0]

    # If the badge was scanned (x_lease_active=True) but the CRM grant has not
    # yet arrived (x_lease_id is empty), applying the topup directly would lose
    # it: the incoming lease_grant overwrites x_wallet_balance with the CRM
    # authoritative balance + x_pending_topup_balance.  Park here instead so
    # process_wallet_lease_grant can merge it safely.
    if not partner.get("x_lease_id"):
        pending = round(float(partner.get("x_pending_topup_balance") or 0.0) + add_amount, 2)
        models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "res.partner", "write",
            [[partner["id"]], {"x_pending_topup_balance": pending}],
        )
        logger.info(
            "[REMOTE_TOPUP] Lease pending for %s — parked €%.2f in x_pending_topup_balance (total pending=%.2f)",
            identity_uuid, add_amount, pending,
        )
        return

    new_balance = float(models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "pos.order", "action_add_wallet_amount",
        [partner["id"], add_amount],
    ) or 0.0)

    models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "pos.order", "action_increment_lease_tx_count",
        [partner["id"]],
    )

    update_xml = build_wallet_balance_update_xml(
        identity_uuid=identity_uuid,
        new_balance=new_balance,
        authority="kassa",
        status="active",
    )
    send_typed_message("wallet_balance_update", update_xml)

    _publish_partner_bus_event(
        uid, models, partner["id"],
        float(partner.get("x_outstanding_amount") or 0.0),
        partner.get("x_payment_status") or "unpaid",
        partner.get("name") or "Unknown",
    )
    logger.info("[REMOTE_TOPUP] ✅ Balance updated for %s: +%.2f → %.2f (reason=%s)",
                identity_uuid, add_amount, new_balance, reason)
    monitor.log(
        "info", "wallet",
        f"wallet_remote_topup processed | identity_uuid={identity_uuid} | "
        f"+{add_amount:.2f} → {new_balance:.2f}"
    )


_pika_conn: pika.BlockingConnection | None = None


def _do_return_all_leases(uid: int, models: OdooModelsProxy) -> None:
    """Return all active leases to CRM. Runs in the main pika IO thread via add_callback_threadsafe."""
    logger.info("[EVENT_ENDED] Returning all active leases")

    active_partners: List[OdooRecord] = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "res.partner", "search_read",
        [[["x_lease_active", "=", True]]],
        {"fields": ["id", "x_user_id", "x_wallet_balance",
                    "x_lease_id", "x_lease_transaction_count"]},
    )

    cleared_ids = []
    for partner in active_partners:
        try:
            identity_uuid = partner.get("x_user_id")
            if not identity_uuid:
                logger.warning("[EVENT_ENDED] Skipping partner %s: no identity_uuid", partner.get("id"))
                continue
            final_balance = float(partner.get("x_wallet_balance") or 0.0)
            lease_id = partner.get("x_lease_id") or ""
            tx_count = int(partner.get("x_lease_transaction_count") or 0)
            xml = build_wallet_lease_return_xml(
                identity_uuid=identity_uuid,
                final_balance=final_balance,
                lease_id=lease_id,
                transaction_count=tx_count,
            )
            send_typed_message("wallet_lease_return", xml)
            cleared_ids.append(partner["id"])
            monitor.log(
                "info", "wallet",
                f"Published wallet_lease_return for identity_uuid={identity_uuid} (event_ended batch)"
            )
        except Exception as exc:
            logger.error("[EVENT_ENDED] Failed to send lease_return for partner %s: %s", partner.get("id"), exc)
            monitor.log(
                "error", "wallet",
                f"event_ended: wallet_lease_return failed for partner_id={partner.get('id')}: {str(exc)[:300]}"
            )

    if cleared_ids:
        models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "res.partner", "write",
            [cleared_ids, {"x_lease_active": False, "x_lease_id": "", "x_lease_transaction_count": 0}],
        )

    logger.info("[EVENT_ENDED] ✅ Returned %d/%d active leases", len(cleared_ids), len(active_partners))
    monitor.log(
        "info", "wallet",
        f"event_ended: returned {len(cleared_ids)}/{len(active_partners)} active leases to CRM"
    )


def process_event_ended(root: Element, uid: int, models: OdooModelsProxy) -> None:
    """Festival over — return every active wallet lease to CRM in one sweep (Flow 6C).

    Delegates to _do_return_all_leases(), which finds all partners with x_lease_active=True
    and sends a wallet_lease_return message for each. This is a fan-out: one event_ended
    triggers N outbound messages (one per leased partner).

    All leases are attempted even if some fail — partial failure is preferable to
    abandoning the sweep, because CRM needs every lease returned to close the event
    accounts correctly.
    """
    body = root.find("body")
    if body is None:
        raise ValueError("event_ended: <body> missing")
    ended_at = (body.findtext("ended_at") or "").strip()
    logger.info("[EVENT_ENDED] Received (ended_at=%s) — returning all active leases", ended_at)
    _do_return_all_leases(uid, models)


def process_cancel_registration(root: Element, uid: int, models: OdooModelsProxy) -> None:
    """Zero out payment obligation for a cancelled attendee (Flow 4).

    The Odoo partner record is NOT deleted or deactivated — history must be preserved
    for audit and for any consumptions the attendee made before cancelling.
    Only x_outstanding_amount is set to 0 and x_payment_status to 'cancelled'.
    """
    body = root.find("body")
    if body is None:
        raise ValueError("cancel_registration: <body> missing")

    identity_uuid = (body.findtext("identity_uuid") or "").strip()
    session_id = (body.findtext("session_id") or "").strip()
    reason = (body.findtext("reason") or "").strip()

    if not identity_uuid:
        raise ValueError("cancel_registration: identity_uuid missing in <body>")

    existing: List[OdooRecord] = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "res.partner", "search_read",
        [[["x_user_id", "=", identity_uuid]]],
        {"fields": ["id", "name"], "limit": 1},
    )

    if existing:
        partner_id = existing[0]["id"]
        models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "res.partner", "write",
            [[partner_id], {
                "x_outstanding_amount": 0.0,
                "x_payment_status": "cancelled",
            }],
        )
        _publish_partner_bus_event(
            uid, models, partner_id,
            0.0, "cancelled", existing[0].get("name") or "Unknown",
        )
        logger.info(
            "[CANCEL_REGISTRATION] ✓ Registration cancelled: Odoo ID=%s | session_id=%s | reason=%s",
            partner_id,
            session_id,
            reason,
        )
        monitor.log(
            "info", "registration",
            f"cancel_registration processed: Odoo ID={partner_id} | reason={reason}"
        )
    else:
        logger.warning("[CANCEL_REGISTRATION] ⚠ Customer not found – no action")


def process_user_sessions_response(root: Element, uid: int, models: OdooModelsProxy) -> None:
    """Handle user_sessions_response from Frontend (RPC reply to user_sessions_request).

    For each session the visitor is registered for, ensure a POS product exists
    in the Inschrijvingskassa under the 'Sessions' category.  Price stays 0.0
    until a future story adds price-sync.
    Binding: kassa.incoming ← kassa.exchange ← frontend.to.kassa.user_sessions_response
    """
    header = root.find("header")
    body = root.find("body")
    correlation_id = header.findtext("correlation_id") if header is not None else "unknown"
    status = (body.findtext("status") or "unknown").strip() if body is not None else "unknown"
    sessions = body.findall(".//session") if body is not None else []
    session_count = len(sessions)

    logger.info(
        "[USER_SESSIONS_RESPONSE] ✅ Received | correlation_id=%s | status=%s | session_count=%d",
        correlation_id, status, session_count,
    )

    if status == "not_found" or session_count == 0:
        logger.warning(
            "[USER_SESSIONS_RESPONSE] No sessions found for correlation_id=%s", correlation_id
        )
        return

    for i, session in enumerate(sessions, 1):
        session_id = session.findtext("session_id") or "?"
        title = session.findtext("title") or "?"
        start = session.findtext("start_datetime") or "?"
        end = session.findtext("end_datetime") or "?"
        loc = session.findtext("location") or "?"
        session_type = session.findtext("session_type") or "?"
        status_val = session.findtext("status") or "?"
        max_att = session.findtext("max_attendees") or "?"
        cur_att = session.findtext("current_attendees") or "?"
        speaker_el = session.find("speaker")
        if speaker_el is not None:
            fn = speaker_el.findtext("contact/first_name") or ""
            ln = speaker_el.findtext("contact/last_name") or ""
            speaker = f"{fn} {ln}".strip() or "-"
        else:
            speaker = "-"
        price_el = session.find("price")
        price = (
            f"{price_el.text} {price_el.get('currency', '')}".strip()
            if price_el is not None else "-"
        )
        logger.info(
            "[USER_SESSIONS_RESPONSE] Session %d/%d: id=%s | '%s' | %s–%s | loc=%s"
            " | type=%s | status=%s | attendees=%s/%s | speaker=%s | price=%s",
            i, session_count, session_id, title, start, end, loc,
            session_type, status_val, cur_att, max_att, speaker, price,
        )

        if title and title != "?":
            session_price: float | None = None
            if price_el is not None:
                try:
                    session_price = float(price_el.text or 0)
                except (ValueError, TypeError):
                    pass
            _ensure_session_product(
                uid, models, title, price=session_price,
                session_id=session_id if session_id != "?" else None,
            )

    logger.info(
        "[USER_SESSIONS_RESPONSE] ✅ %d session product(s) ensured in Inschrijvingskassa"
        " | correlation_id=%s",
        session_count, correlation_id,
    )
    monitor.log(
        "info", "session",
        f"user_sessions_response processed | {session_count} session(s) ensured | "
        f"correlation_id={correlation_id}"
    )

    try:
        notified = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "pos.session", "kassa_notify_product_update", [[]],
        )
        logger.info(
            "[USER_SESSIONS_RESPONSE] Bus notification sent to %d open POS session(s)", notified
        )
    except Exception as exc:
        logger.warning("[USER_SESSIONS_RESPONSE] Could not push bus notification: %s", exc)


def _parse_session_list(raw: str) -> List[Dict[str, Any]]:
    """Parse x_session_title JSON; normalise plain-string entries to dict format."""
    if not raw:
        return []
    try:
        entries = json.loads(raw)
        if not isinstance(entries, list):
            entries = [entries]
    except (json.JSONDecodeError, ValueError):
        entries = [raw]
    result = []
    for e in entries:
        if isinstance(e, dict):
            result.append(e)
        elif isinstance(e, str) and e.strip():
            result.append({"session_id": "", "title": e.strip(), "price": None})
    return result


def _safe_price(value: Any) -> Optional[float]:
    """Convert a stored price value to float, or None if missing/non-numeric."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def process_user_registered(root: Element, uid: int, models: OdooModelsProxy) -> None:
    """Handle user_registered from Frontend (dual-publish, contract §5.5).

    Adds the session entry (with price) to the partner's x_session_title list and
    accumulates x_outstanding_amount. If the partner does not exist yet (race with
    new_registration), logs a warning and does nothing — new_registration will
    create the record with full profile data.
    Binding: kassa.incoming ← kassa.exchange ← kassa.incoming.user_registered
    """
    body = root.find("body")
    if body is None:
        raise ValueError("user_registered: <body> missing")

    customer = body.find("customer")
    if customer is None:
        raise ValueError("user_registered: <customer> missing in <body>")

    identity_uuid = (customer.findtext("identity_uuid") or "").strip()
    session_id = (customer.findtext("session_id") or "").strip()
    if not identity_uuid:
        raise ValueError("user_registered: identity_uuid missing")
    if not session_id:
        raise ValueError("user_registered: session_id missing")

    session_title = (body.findtext("session_title") or "").strip()
    payment_status = (body.findtext("payment_status") or "pending").strip()

    price_el = body.find("price")
    price: Optional[float] = None
    if price_el is not None and price_el.text:
        try:
            price = float(price_el.text.strip())
        except (ValueError, TypeError):
            pass

    existing: List[OdooRecord] = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "res.partner", "search_read",
        [[["x_user_id", "=", identity_uuid]]],
        {"fields": ["id", "name", "x_session_title", "x_outstanding_amount"], "limit": 1},
    )

    if not existing:
        logger.warning(
            "[USER_REGISTERED] ⚠ Partner not found for identity_uuid=%s — "
            "will be handled when new_registration arrives", identity_uuid,
        )
        return

    partner_id = existing[0]["id"]
    sessions = _parse_session_list(existing[0].get("x_session_title") or "")
    current_outstanding = round(float(existing[0].get("x_outstanding_amount") or 0.0), 2)

    is_new = not any(s.get("session_id") == session_id for s in sessions)
    if is_new:
        sessions.append({"session_id": session_id, "title": session_title, "price": price})
        # Additive: add this session's price to the current authoritative outstanding.
        # Recalculating from x_session_title would erase amounts set by new_registration
        # (CRM payment_due) or zeroed by order_poller after payment.
        new_outstanding = round(current_outstanding + (price if price is not None else 0.0), 2)
    else:
        new_outstanding = current_outstanding

    models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "res.partner", "write",
        [[partner_id], {
            "x_session_title": json.dumps(sessions),
            "x_outstanding_amount": new_outstanding,
            "x_payment_status": payment_status,
        }],
    )
    _publish_partner_bus_event(
        uid, models, partner_id,
        new_outstanding, payment_status, existing[0].get("name") or "",
    )
    logger.info(
        "[USER_REGISTERED] ✓ Session added | Odoo ID=%s | session_id=%s | price=%s | outstanding=%.2f",
        partner_id, session_id, price, new_outstanding,
    )
    monitor.log(
        "info", "registration",
        f"user_registered: session added | partner={partner_id} | session_id={session_id}"
    )


def process_user_unregistered(root: Element, uid: int, models: OdooModelsProxy) -> None:
    """Handle user_unregistered from Frontend (dual-publish, contract §5.5b).

    Removes the session entry from the partner's x_session_title list and
    recalculates x_outstanding_amount.
    Binding: kassa.incoming ← kassa.exchange ← kassa.incoming.user_unregistered
    """
    body = root.find("body")
    if body is None:
        raise ValueError("user_unregistered: <body> missing")

    identity_uuid = (body.findtext("identity_uuid") or "").strip()
    session_id = (body.findtext("session_id") or "").strip()
    if not identity_uuid:
        raise ValueError("user_unregistered: identity_uuid missing")
    if not session_id:
        raise ValueError("user_unregistered: session_id missing")

    existing: List[OdooRecord] = models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "res.partner", "search_read",
        [[["x_user_id", "=", identity_uuid]]],
        {"fields": ["id", "name", "x_session_title", "x_outstanding_amount", "x_payment_status"], "limit": 1},
    )

    if not existing:
        logger.warning(
            "[USER_UNREGISTERED] ⚠ Partner not found for identity_uuid=%s — no action",
            identity_uuid,
        )
        return

    partner_id = existing[0]["id"]
    sessions = _parse_session_list(existing[0].get("x_session_title") or "")
    current_outstanding = round(float(existing[0].get("x_outstanding_amount") or 0.0), 2)
    current_status = existing[0].get("x_payment_status") or "pending"

    removed = next((s for s in sessions if s.get("session_id") == session_id), None)
    sessions = [s for s in sessions if s.get("session_id") != session_id]

    removed_price = _safe_price(removed.get("price")) if removed else None
    if removed_price is not None:
        # Subtractive: remove only this session's price from the authoritative outstanding.
        # Clamped at 0 so a partially-paid balance never goes negative.
        new_outstanding = round(max(0.0, current_outstanding - removed_price), 2)
    else:
        new_outstanding = current_outstanding

    # Only flip to "paid" when the debt is actually cleared; preserve the current status
    # otherwise so a "paid" partner who partially unregisters does not revert to "pending".
    status = "paid" if new_outstanding == 0.0 else current_status

    models.execute_kw(
        ODOO_DB, uid, ODOO_PASS,
        "res.partner", "write",
        [[partner_id], {
            "x_session_title": json.dumps(sessions),
            "x_outstanding_amount": new_outstanding,
            "x_payment_status": status,
        }],
    )
    _publish_partner_bus_event(
        uid, models, partner_id,
        new_outstanding, status, existing[0].get("name") or "",
    )
    logger.info(
        "[USER_UNREGISTERED] ✓ Session removed | Odoo ID=%s | session_id=%s | outstanding=%.2f",
        partner_id, session_id, new_outstanding,
    )
    monitor.log(
        "info", "registration",
        f"user_unregistered: session removed | partner={partner_id} | session_id={session_id}"
    )


def process_session_created(root: Element, uid: int, models: OdooModelsProxy) -> None:
    """Handle session_created from Frontend.

    A session being created has no user linked to it — it describes the session
    itself (title, dates, price, etc.). Kassa only needs to ensure the matching
    POS product exists so it is ready when visitors scan their badge.
    Binding: kassa.incoming ← frontend.to.kassa.session.created
    """
    body = root.find("body")
    if body is None:
        raise ValueError("session_created: <body> missing")

    session_id = (body.findtext("session_id") or "").strip()
    title = (body.findtext("title") or "").strip()
    if not session_id or not title:
        raise ValueError("session_created: session_id or title missing")

    price_el = body.find("price")
    price: Optional[float] = None
    if price_el is not None and price_el.text:
        try:
            price = float(price_el.text.strip())
        except (ValueError, TypeError):
            pass

    _ensure_session_product(uid, models, title, price=price, session_id=session_id)
    logger.info("[SESSION_CREATED] ✓ POS product ensured for session '%s' (id=%s)", title, session_id)
    monitor.log(
        "info", "session",
        f"session_created: POS product ensured | session_id={session_id} | title={title}"
    )

    try:
        notified = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "pos.session", "kassa_notify_product_update", [[]],
        )
        logger.info("[SESSION_CREATED] Bus notification sent to %d open POS session(s)", notified)
    except Exception as exc:
        logger.warning("[SESSION_CREATED] Could not push bus notification: %s", exc)


def process_session_updated(root: Element, uid: int, models: OdooModelsProxy) -> None:
    """Handle session_updated from Frontend.

    A session update has no user linked — it describes changes to the session
    itself (new title, price, dates, etc.). Kassa updates the matching POS
    product so the correct name/price is shown at scan time.
    Binding: kassa.incoming ← frontend.to.kassa.session.updated
    """
    body = root.find("body")
    if body is None:
        raise ValueError("session_updated: <body> missing")

    session_id = (body.findtext("session_id") or "").strip()
    title = (body.findtext("title") or "").strip()
    if not session_id or not title:
        raise ValueError("session_updated: session_id or title missing")

    price_el = body.find("price")
    price: Optional[float] = None
    if price_el is not None and price_el.text:
        try:
            price = float(price_el.text.strip())
        except (ValueError, TypeError):
            pass

    _ensure_session_product(uid, models, title, price=price, session_id=session_id)
    logger.info("[SESSION_UPDATED] ✓ POS product updated for session '%s' (id=%s)", title, session_id)
    monitor.log(
        "info", "session",
        f"session_updated: POS product updated | session_id={session_id} | title={title}"
    )

    try:
        notified = models.execute_kw(
            ODOO_DB, uid, ODOO_PASS,
            "pos.session", "kassa_notify_product_update", [[]],
        )
        logger.info("[SESSION_UPDATED] Bus notification sent to %d open POS session(s)", notified)
    except Exception as exc:
        logger.warning("[SESSION_UPDATED] Could not push bus notification: %s", exc)


def process_session_deleted(root: Element, uid: int, models: OdooModelsProxy) -> None:
    """Handle session_deleted from Frontend.

    A session deletion has no user linked — the session itself is gone.
    Kassa does NOT delete the POS product: visitors who already paid or are
    mid-transaction may still need it. Log and ack.
    Binding: kassa.incoming ← frontend.to.kassa.session.deleted
    """
    body = root.find("body")
    if body is None:
        raise ValueError("session_deleted: <body> missing")

    session_id = (body.findtext("session_id") or "").strip()
    if not session_id:
        raise ValueError("session_deleted: session_id missing")

    reason = (body.findtext("reason") or "").strip()
    logger.info(
        "[SESSION_DELETED] Session id=%s removed from system%s — POS product kept.",
        session_id, f" (reason: {reason})" if reason else "",
    )
    reason_suffix = f" | reason={reason}" if reason else ""
    monitor.log(
        "info", "session",
        f"session_deleted received | session_id={session_id} | POS product kept{reason_suffix}"
    )


# ── Central message processing ─────────────────────────────────────────────────
def process_message(ch, method, properties, body):
    """
    RabbitMQ delivery callback — called once per message by pika.

    Processing pipeline:
      1. Parse XML             — reject immediately if not valid XML
      2. Read header           — extract message_id and type
      3. Idempotency check     — skip if message_id seen before in this session
      4. XSD validation        — reject if message does not match its schema
      5. Odoo connection       — authenticate fresh per message (stateless)
      6. Business logic        — dispatch to the correct process_* function
      7. ACK + remember ID     — cache message_id only after successful handling

    On any validation or business-logic error:
      - A system_error is forwarded to kassa.errors via send_error_to_queue.
      - Validation and business errors use basic_nack(requeue=False).
      - Odoo connection/auth errors are retried up to MAX_RETRIES.
    """
    xml_text = body.decode("utf-8")
    related_message_id = None

    try:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.error("[RECEIVER] ❌ XML parse error: %s", e)
            monitor.log("error", "xml_validation", f"Unparseable XML received: {str(e)[:500]}")
            send_error_to_queue("invalid_xml_format", None, f"XML could not be parsed: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        header = root.find("header")
        related_message_id = header.findtext("message_id") if header is not None else None
        msg_type = header.findtext("type") if header is not None else None

        if not msg_type:
            send_error_to_queue("invalid_xml_format", related_message_id, "Message type missing")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        if related_message_id and is_duplicate(related_message_id, track_if_new=False):
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        logger.info("[RECEIVER] Received: type=%s | message_id=%s", msg_type, related_message_id)

        try:
            validate_xml(xml_text, msg_type)
        except ValueError as e:
            logger.error("[RECEIVER] ❌ Validation failure for '%s': %s", msg_type, e)
            monitor.log(
                "error", "xml_validation",
                f"Validation failure for {msg_type} (ID: {related_message_id or 'unknown'}): {str(e)[:500]}"
            )
            send_error_to_queue("invalid_xml_format", related_message_id, str(e))
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        source = header.findtext("source") if header is not None else "unknown"
        monitor.log(
            "info", "xml_validation",
            f"Received {msg_type} from {source} (ID: {related_message_id or 'unknown'}). Validation: Success."
        )

        if msg_type not in SCHEMA_MAP:
            raise ValueError(f"Unknown message type: '{msg_type}'")

        # user_event is informational only — no Odoo action needed.
        # Handle it here so we never open an Odoo connection for it, which
        # would cause spurious retries when Odoo is temporarily unreachable.
        if msg_type == "user_event":
            logger.info("[RECEIVER] user_event received (no Odoo action): %s", related_message_id)
            if related_message_id:
                _remember_message_id(related_message_id)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        uid, models = get_odoo_connection()

        if msg_type == "new_registration":
            process_new_registration(root, uid, models)
        elif msg_type == "user_registered":
            process_user_registered(root, uid, models)
        elif msg_type == "user_unregistered":
            process_user_unregistered(root, uid, models)
        elif msg_type == "profile_update":
            process_profile_update(root, uid, models)
        elif msg_type == "badge_scanned":
            process_badge_scan(root, uid, models)
        elif msg_type == "cancel_registration":
            process_cancel_registration(root, uid, models)
        elif msg_type == "wallet_lease_grant":
            process_wallet_lease_grant(root, uid, models)
        elif msg_type == "wallet_remote_topup":
            process_wallet_remote_topup(root, uid, models)
        elif msg_type == "event_ended":
            process_event_ended(root, uid, models)
        elif msg_type == "user_sessions_response":
            process_user_sessions_response(root, uid, models)
        elif msg_type == "session_created":
            process_session_created(root, uid, models)
        elif msg_type == "session_updated":
            process_session_updated(root, uid, models)
        elif msg_type == "session_deleted":
            process_session_deleted(root, uid, models)

        if related_message_id:
            _remember_message_id(related_message_id)
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except ValueError as e:
        error_str = str(e)
        if "Unknown message type" in error_str:
            code = "unknown_message_type"
        else:
            code = "invalid_xml_format"
        logger.error("[RECEIVER] ❌ %s: %s", code, e)
        send_error_to_queue(code, related_message_id, error_str)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    except ConnectionError as e:
        retries = properties.headers.get("x-retry-count", 0) if properties and properties.headers else 0
        if retries < MAX_RETRIES:
            logger.warning("[RECEIVER] ⚠ Odoo error (retry %d/%d): %s", retries + 1, MAX_RETRIES, e)
            new_headers = properties.headers.copy() if properties and properties.headers else {}
            new_headers["x-retry-count"] = retries + 1
            ch.basic_publish(
                exchange="", routing_key=RETRY_QUEUE, body=body,
                properties=pika.BasicProperties(headers=new_headers, delivery_mode=2)
            )
            ch.basic_ack(delivery_tag=method.delivery_tag)
        else:
            logger.error("[RECEIVER] ❌ Max retries reached: %s", e)
            monitor.log(
                "error", "system_error",
                f"Receiver: Max retries reached for message {related_message_id}: {str(e)[:500]}"
            )
            send_error_to_queue("odoo_api_error", related_message_id, f"Max retries reached: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    except Exception as e:
        logger.error("[RECEIVER] ❌ Unexpected error: %s", e)
        monitor.log(
            "error", "system_error",
            f"Unexpected receiver error for {related_message_id or 'unknown'}: {str(e)[:500]}"
        )
        send_error_to_queue("odoo_api_error", related_message_id, str(e))
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


# ── RabbitMQ connection and startup ───────────────────────────────────────────

def connect_to_rabbitmq():
    """Open a new blocking connection to RabbitMQ using environment credentials."""
    required = require_env("RABBIT_HOST", "RABBIT_USER", "RABBIT_PASS")
    credentials = pika.PlainCredentials(required["RABBIT_USER"], required["RABBIT_PASS"])
    params = pika.ConnectionParameters(
        host=required["RABBIT_HOST"], port=RABBIT_PORT, virtual_host=RABBIT_VHOST, credentials=credentials,
    )
    return pika.BlockingConnection(params)


def start_listening():
    """Connect to RabbitMQ and start consuming."""
    global _pika_conn
    conn = connect_to_rabbitmq()
    _pika_conn = conn
    channel = conn.channel()

    try:
        setup_exchange(channel)
        # Subscribe to user.events fanout — handles UserCreated and UserDeleted
        if os.environ.get("SUBSCRIBE_USER_EVENTS", "True").lower() not in ("0", "false", "no"):
            try:
                channel.exchange_declare(exchange="user.events", exchange_type="fanout", durable=True)
                ue_queue = f"{QUEUE_NAME}.user.events"
                channel.queue_declare(queue=ue_queue, durable=True)
                channel.queue_bind(exchange="user.events", queue=ue_queue)

                def _user_events_callback(ch2, method2, props2, body2):
                    try:
                        txt = body2.decode("utf-8")
                        validate_xml(txt, "user_event")
                        import defusedxml.ElementTree as _ET
                        _root = _ET.fromstring(txt)
                        event_type = (_root.findtext("event") or "").strip()
                        master_uuid = (_root.findtext("master_uuid") or "").strip()
                        if event_type == "UserDeleted" and master_uuid:
                            _uid2, _models2 = get_odoo_connection()
                            _existing = _models2.execute_kw(
                                ODOO_DB, _uid2, ODOO_PASS,
                                "res.partner", "search_read",
                                [[[["x_user_id", "=", master_uuid]]]],
                                {"fields": ["id", "name"], "limit": 1},
                            )
                            if _existing:
                                _pid = _existing[0]["id"]
                                _models2.execute_kw(
                                    ODOO_DB, _uid2, ODOO_PASS,
                                    "res.partner", "write",
                                    [[_pid], {
                                        "x_wallet_balance": 0.0,
                                        "x_outstanding_amount": 0.0,
                                        "x_payment_status": "deleted",
                                    }],
                                )
                                logger.info(
                                    "[USER_EVENTS] UserDeleted: wallet zeroed for partner=%s uuid=%s",
                                    _existing[0]["name"], master_uuid,
                                )
                            else:
                                logger.info(
                                    "[USER_EVENTS] UserDeleted: no Odoo partner found for uuid=%s — skipped",
                                    master_uuid,
                                )
                        else:
                            logger.info("[USER_EVENTS] Received user event type=%s uuid=%s", event_type, master_uuid)
                    except Exception as _ue_exc:
                        logger.warning("[USER_EVENTS] Error processing user event: %s", _ue_exc)
                    ch2.basic_ack(delivery_tag=method2.delivery_tag)

                channel.basic_consume(queue=ue_queue, on_message_callback=_user_events_callback)
                logger.info("[RECEIVER] Subscribed to user.events fanout via queue %s", ue_queue)
            except Exception as e:
                logger.warning("[RECEIVER] Could not bind to user.events fanout: %s", e)
                monitor.log("warning", "system_error", f"Could not bind to user.events fanout: {str(e)[:300]}")
        dead_letter_exchange = DLX_NAME
        if DLX_NAME != EXCHANGE_NAME:
            channel.exchange_declare(exchange=DLX_NAME, exchange_type="direct", durable=True)
        channel.queue_declare(queue=DLQ_NAME, durable=True)
        channel.queue_bind(exchange=dead_letter_exchange, queue=DLQ_NAME, routing_key=DLQ_ROUTING_KEY)

        channel.queue_declare(
            queue=QUEUE_NAME, durable=True,
            arguments={"x-dead-letter-exchange": dead_letter_exchange,
                       "x-dead-letter-routing-key": DLQ_ROUTING_KEY}
        )

        channel.queue_declare(
            queue=RETRY_QUEUE, durable=True,
            arguments={
                "x-message-ttl": RETRY_DELAY_MS,
                "x-dead-letter-exchange": EXCHANGE_NAME,
                "x-dead-letter-routing-key": f"{QUEUE_NAME}.retry-recovery",
            }
        )
        channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME,
                           routing_key=f"{QUEUE_NAME}.retry-recovery")
        channel.queue_bind(exchange=EXCHANGE_NAME, queue=QUEUE_NAME, routing_key=f"{QUEUE_NAME}.#")

    except pika.exceptions.ChannelClosedByBroker as exc:
        # If the broker reports PRECONDITION_FAILED (406), it usually means the
        # queue/exchange already exists with different arguments. Do not crash
        # the whole receiver — attempt to open a fresh channel and continue
        # consuming from the existing queue without trying to redeclare it.
        if getattr(exc, "reply_code", None) == 406:
            msg_template = (
                "RabbitMQ topology conflict (406 PRECONDITION_FAILED) while declaring "
                "exchange=%s "
                "queue=%s "
                "dlq=%s "
                "retry_queue=%s: %s"
            )
            logger.critical(
                msg_template,
                EXCHANGE_NAME,
                QUEUE_NAME,
                DLQ_NAME,
                RETRY_QUEUE,
                getattr(exc, "reply_text", ""),
            )
            monitor.log("error", "system_error",
                        f"RabbitMQ topology conflict (406) on exchange={EXCHANGE_NAME} "
                        f"queue={QUEUE_NAME}: {getattr(exc, 'reply_text', '')[:300]}")
            # Try to recover: open a fresh connection/channel and skip topology setup
            try:
                try:
                    conn.close()
                except Exception:
                    pass
                conn = connect_to_rabbitmq()
                _pika_conn = conn
                channel = conn.channel()
                info_msg = (
                    "[RECEIVER] Recovered with existing broker topology; "
                    "will consume from existing queue %s"
                )
                logger.info(info_msg, QUEUE_NAME)
            except Exception as e:
                logger.critical("[RECEIVER] Could not recover from topology conflict: %s", e)
                raise
        else:
            raise
    except Exception:
        logger.critical("Failed to setup RabbitMQ topology")
        raise

    channel.basic_qos(prefetch_count=1)
    # Optional: flush buffer on start
    try:
        flushed_ids = flush_buffer()
        if flushed_ids:
            uid, models = get_odoo_connection()
            models.execute_kw(
                ODOO_DB,
                uid,
                ODOO_PASS,
                'pos.order',
                'write',
                [list(set(flushed_ids)), {'x_rabbitmq_sent': True}],
            )
    except Exception as e:
        logger.warning("Could not flush on startup: %s", e)
        msg = f"Startup flush failure: {str(e)[:500]}"
        monitor.log("warning", "system_error", msg)

    # Declare frontend.exchange and bind Frontend → Kassa session routing keys.
    # Frontend owns this exchange and publishes session lifecycle + RPC responses to it.
    try:
        channel.exchange_declare(exchange=FRONTEND_EXCHANGE, exchange_type="topic", durable=True)
        for routing_key in (
            "frontend.to.kassa.user_sessions_response",
            "frontend.to.kassa.session.created",
            "frontend.to.kassa.session.updated",
            "frontend.to.kassa.session.deleted",
        ):
            channel.queue_bind(
                exchange=FRONTEND_EXCHANGE,
                queue=QUEUE_NAME,
                routing_key=routing_key,
            )
        logger.info("[RECEIVER] ✅ Bound Frontend session routing keys on %s", FRONTEND_EXCHANGE)
    except Exception as e:
        logger.warning("[RECEIVER] Could not bind Frontend session routing keys: %s", e)
        monitor.log("warning", "session",
                    f"Could not bind Frontend session routing keys on {FRONTEND_EXCHANGE}: {str(e)[:300]}")

    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_message)
    logger.info("[RECEIVER] ✓ Listening on queue: %s", QUEUE_NAME)
    channel.start_consuming()


if __name__ == "__main__":
    start_listening()
