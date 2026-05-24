"""
partner_identity_poller.py — Polls Odoo for unlinked partners and links them via Identity Service.

This poller implements the "Create Local Odoo Customer With Identity master_uuid" flow.
It ensures that every Odoo customer with an email address is associated with a
global master_uuid from the Identity Service, without sending CRM messages.

Business Rules:
- Source of truth for identity is the Identity Service.
- No locally generated UUIDs are used.
- If Identity is unavailable, the status is set to 'pending' for retry.
- Existing links in Odoo (same email) are reused.
"""

import logging
import os
import re
import time
import xmlrpc.client  # nosec
import defusedxml.xmlrpc
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

import identity_client
from config_utils import require_env
from monitoring import monitor

defusedxml.xmlrpc.monkey_patch()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Minimum seconds between retries for partners in 'error' state
_ERROR_RETRY_AFTER = int(os.environ.get("IDENTITY_ERROR_RETRY_AFTER", "3600"))

# Module logger
logger = logging.getLogger(__name__)


class PartnerIdentityPoller:
    def __init__(self):
        """Set up Odoo credentials from environment; Odoo connection is established via connect_odoo().

        Polling interval is read at runtime from IDENTITY_POLL_INTERVAL env var (default 10 s)
        and passed to poll() by main.py. This class does not hold an interval itself so it can
        be re-used with different cadences in tests.
        """
        env = require_env("ODOO_URL", "ODOO_DB", "ODOO_USER", "ODOO_PASS")
        self.odoo_url = env["ODOO_URL"]
        self.odoo_db = env["ODOO_DB"]
        self.odoo_user = env["ODOO_USER"]
        self.odoo_pass = env["ODOO_PASS"]

        self.uid = None
        self.models = None

    def connect_odoo(self) -> bool:
        """Open an XML-RPC session with Odoo and store ``uid`` and ``models`` on ``self``.

        Must be called once before ``poll()`` is invoked. main.py calls this right
        after instantiating the poller and aborts startup if it returns ``False``
        (no point starting a poller that cannot talk to Odoo).

        Returns:
            ``True`` on successful authentication, ``False`` otherwise.
        """
        try:
            common = xmlrpc.client.ServerProxy(f"{self.odoo_url}/xmlrpc/2/common", allow_none=True)
            self.uid = common.authenticate(self.odoo_db, self.odoo_user, self.odoo_pass, {})
            if self.uid:
                self.models = xmlrpc.client.ServerProxy(f"{self.odoo_url}/xmlrpc/2/object", allow_none=True)
                logger.info("✅ PartnerIdentityPoller: Odoo connection established")
                return True
            logger.error("❌ PartnerIdentityPoller: Odoo authentication failed")
            monitor.log("error", "identity", "Odoo authentication failed — partner identity poller cannot start")
            return False
        except Exception as e:
            logger.error("❌ PartnerIdentityPoller: Connection error: %s", e)
            monitor.log("error", "identity", f"Odoo connection error: {e}")
            return False

    def _get_unlinked_partners(self) -> List[Dict[str, Any]]:
        """Find partners with email, no x_user_id, and status != 'linked'."""
        try:
            # Domain: (email != False) AND (x_user_id == False) AND (x_identity_status != 'linked')
            domain = [
                ["email", "!=", False],
                ["x_user_id", "=", False],
                ["x_identity_status", "!=", "linked"]
            ]
            partner_ids = self.models.execute_kw(
                self.odoo_db, self.uid, self.odoo_pass,
                "res.partner", "search",
                [domain],
                {"limit": 100}
            )
            if not partner_ids:
                return []

            return self.models.execute_kw(
                self.odoo_db, self.uid, self.odoo_pass,
                "res.partner", "read",
                [partner_ids, ["id", "name", "email", "x_identity_status", "x_identity_last_sync"]]
            )
        except Exception as e:
            logger.error("❌ Error fetching unlinked partners: %s", e)
            monitor.log("error", "identity", f"Failed to fetch unlinked partners from Odoo: {e}")
            return []

    def _find_existing_link_in_odoo(self, email: str) -> Optional[str]:
        """Check if another partner with this email already has an x_user_id."""
        try:
            domain = [
                ["email", "=", email],
                ["x_user_id", "!=", False],
            ]
            existing = self.models.execute_kw(
                self.odoo_db, self.uid, self.odoo_pass,
                "res.partner", "search_read",
                [domain],
                {"fields": ["x_user_id"], "limit": 1, "order": "active desc, id asc"}
            )
            if existing:
                return existing[0]["x_user_id"]
            return None
        except Exception as e:
            logger.warning("⚠️ Error checking existing links in Odoo for %s: %s", email, e)
            monitor.log("warning", "identity", f"Failed to check existing identity link for {email}: {e}")
            return None

    def process_partner(self, partner: Dict[str, Any]):
        """Resolve and store the Identity master_uuid for a single unlinked partner.

        Resolution order:
        1. Validate the email address format (error-state partners are skipped during
           their cooldown window to avoid hammering the Identity Service on repeated failures).
        2. Check if another Odoo partner with the same email already has an x_user_id —
           if so, reuse it without making an RPC call (deduplication within Odoo).
        3. Call identity.user.create.request.  Because create is idempotent, this is safe
           to retry.  On EMAIL_ALREADY_EXISTS the service falls back to lookup_by_email.
        4. Write the returned master_uuid to res.partner.x_user_id via _update_partner().

        A locally generated UUID is never used as fallback — per contract, the Identity
        Service is the only source of truth for master UUIDs.
        """
        partner_id = partner["id"]
        raw_email = partner.get("email") or ""
        email = raw_email.strip() if isinstance(raw_email, str) else ""
        name = partner.get("name") or email

        # Validate email format before contacting Identity Service
        if not _EMAIL_RE.match(email):
            logger.error("Invalid email for partner %s: %r — marking as error", partner_id, email)
            monitor.log("error", "identity",
                        f"Partner {partner_id} has invalid email {email!r} — skipping identity link")
            self._update_partner(partner_id, None, "error", "Invalid email address")
            return

        # Skip error-state partners that were synced recently to avoid hammering Identity
        if partner.get("x_identity_status") == "error":
            last_sync = partner.get("x_identity_last_sync")
            if last_sync and isinstance(last_sync, str):
                try:
                    last_sync_dt = datetime.strptime(last_sync, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    sync_age = (datetime.now(timezone.utc) - last_sync_dt).total_seconds()
                    if sync_age < _ERROR_RETRY_AFTER:
                        return
                except ValueError:
                    pass

        logger.info("Processing unlinked partner: %s (%s)", name, email)

        # 1. Check for existing link in Odoo
        existing_uuid = self._find_existing_link_in_odoo(email)
        if existing_uuid:
            logger.info("Reusing existing x_user_id %s for %s", existing_uuid, email)
            monitor.log("info", "identity", f"Partner {email} linked via existing Odoo record (uuid={existing_uuid})")
            self._update_partner(partner_id, existing_uuid, "linked")
            return

        # 2. Call Identity Service
        try:
            master_uuid = None
            try:
                # Try to create
                master_uuid = identity_client.create_user(email, source_system="kassa")
                logger.info("Created new Identity user for %s: %s", email, master_uuid)
                monitor.log("info", "identity", f"New Identity user created for {email} (uuid={master_uuid})")
            except identity_client.IdentityEmailAlreadyExists:
                # Fallback to lookup
                logger.info("Email %s already exists in Identity, performing lookup", email)
                result = identity_client.lookup_by_email(email)
                if result and result.get("master_uuid"):
                    master_uuid = result["master_uuid"]
                    logger.info("Found existing master_uuid for %s: %s", email, master_uuid)
                    monitor.log("info", "identity",
                                f"Partner {email} resolved via Identity lookup (uuid={master_uuid})")
                else:
                    logger.error("Identity lookup failed for existing email %s", email)
                    monitor.log("error", "identity", f"Identity lookup failed for existing email {email}")
                    self._update_partner(partner_id, None, "error", "Identity lookup failed for existing email")
                    return

            if master_uuid:
                self._update_partner(partner_id, master_uuid, "linked")
            else:
                monitor.log("error", "identity", f"No master_uuid returned from Identity for {email}")
                self._update_partner(partner_id, None, "error", "No master_uuid returned from Identity")

        except identity_client.IdentityUnavailableError:
            logger.warning("Identity Service unavailable, marking %s as pending", email)
            monitor.log("warning", "identity", f"Identity Service unavailable — partner {email} marked pending")
            self._update_partner(partner_id, None, "pending")
        except Exception as e:
            logger.error("Unexpected error linking partner %s: %s", email, e)
            monitor.log("error", "identity", f"Unexpected error linking partner {email}: {e}")
            self._update_partner(partner_id, None, "error", str(e))

    def _update_partner(self, partner_id: int, x_user_id: Optional[str], status: str, error_msg: Optional[str] = None):
        """Persist identity link result to Odoo.

        Always writes x_identity_status and x_identity_last_sync together so ops can
        audit when each partner was last processed, regardless of outcome. The timestamp
        is also how the error-cooldown logic in process_partner measures elapsed time.

        x_rabbitmq_error is reused for identity error messages to avoid creating a
        separate custom field — the field semantics are compatible (both track last
        integration failure reason).
        """
        vals = {
            "x_identity_status": status,
            "x_identity_last_sync": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        }
        if x_user_id:
            vals["x_user_id"] = x_user_id
        if error_msg:
            # Reuse x_rabbitmq_error for logging identity errors too
            vals["x_rabbitmq_error"] = f"Identity Link Error: {error_msg}"

        try:
            self.models.execute_kw(
                self.odoo_db, self.uid, self.odoo_pass,
                "res.partner", "write",
                [[partner_id], vals]
            )
        except Exception as e:
            logger.error("❌ Failed to update partner %s in Odoo: %s", partner_id, e)
            monitor.log("error", "identity", f"Failed to write identity status for partner {partner_id} in Odoo: {e}")

    def poll(self, interval: int = 10):
        """Main polling loop: find unlinked partners and call process_partner() for each.

        Capped at 100 partners per cycle to prevent one very large backlog from
        blocking the loop for too long. Partners that cannot be processed (Identity
        Service unavailable, invalid email) are left in pending/error state and
        re-evaluated on the next cycle subject to the error-cooldown rule.

        The loop is intentionally resilient: an unexpected exception logs the error
        and sleeps before retrying, rather than crashing the thread.
        """
        logger.info("Partner Identity Poller started (interval: %ds)", interval)
        while True:
            try:
                partners = self._get_unlinked_partners()
                if partners:
                    error_partners = [p for p in partners if p.get("x_identity_status") == "error"]
                    if error_partners:
                        logger.warning(
                            "⚠️ %d partner(s) stuck in identity error state — "
                            "check x_rabbitmq_error field in Odoo (IDs: %s)",
                            len(error_partners),
                            ", ".join(str(p["id"]) for p in error_partners),
                        )
                    logger.info("Found %d unlinked partners", len(partners))
                    for p in partners:
                        self.process_partner(p)

                time.sleep(interval)
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error("Unexpected error in PartnerIdentityPoller loop: %s", e)
                time.sleep(interval)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    poller = PartnerIdentityPoller()
    if poller.connect_odoo():
        poller.poll()
