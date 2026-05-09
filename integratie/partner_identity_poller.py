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
import time
import xmlrpc.client  # nosec
from datetime import datetime
from typing import List, Dict, Any, Optional

import identity_client
from config_utils import require_env


class PartnerIdentityPoller:
    def __init__(self):
        env = require_env("ODOO_URL", "ODOO_DB", "ODOO_USER", "ODOO_PASS")
        self.odoo_url = env["ODOO_URL"]
        self.odoo_db = env["ODOO_DB"]
        self.odoo_user = env["ODOO_USER"]
        self.odoo_pass = env["ODOO_PASS"]

        self.uid = None
        self.models = None

    def connect_odoo(self) -> bool:
        try:
            common = xmlrpc.client.ServerProxy(f"{self.odoo_url}/xmlrpc/2/common", allow_none=True)
            self.uid = common.authenticate(self.odoo_db, self.odoo_user, self.odoo_pass, {})
            if self.uid:
                self.models = xmlrpc.client.ServerProxy(f"{self.odoo_url}/xmlrpc/2/object", allow_none=True)
                logger.info("✅ PartnerIdentityPoller: Odoo connection established")
                return True
            logger.error("❌ PartnerIdentityPoller: Odoo authentication failed")
            return False
        except Exception as e:
            logger.error("❌ PartnerIdentityPoller: Connection error: %s", e)
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
                [partner_ids, ["id", "name", "email", "x_identity_status"]]
            )
        except Exception as e:
            logger.error("❌ Error fetching unlinked partners: %s", e)
            return []

    def _find_existing_link_in_odoo(self, email: str) -> Optional[str]:
        """Check if another partner with this email already has an x_user_id."""
        try:
            domain = [
                ["email", "=", email],
                ["x_user_id", "!=", False]
            ]
            existing = self.models.execute_kw(
                self.odoo_db, self.uid, self.odoo_pass,
                "res.partner", "search_read",
                [domain],
                {"fields": ["x_user_id"], "limit": 1}
            )
            if existing:
                return existing[0]["x_user_id"]
            return None
        except Exception as e:
            logger.warning("⚠️ Error checking existing links in Odoo for %s: %s", email, e)
            return None

    def process_partner(self, partner: Dict[str, Any]):
        partner_id = partner["id"]
        email = partner["email"].strip()
        name = partner.get("name") or email

        logger.info("Processing unlinked partner: %s (%s)", name, email)

        # 1. Check for existing link in Odoo
        existing_uuid = self._find_existing_link_in_odoo(email)
        if existing_uuid:
            logger.info("Reusing existing x_user_id %s for %s", existing_uuid, email)
            self._update_partner(partner_id, existing_uuid, "linked")
            return

        # 2. Call Identity Service
        try:
            master_uuid = None
            try:
                # Try to create
                master_uuid = identity_client.create_user(email, source_system="kassa")
                logger.info("Created new Identity user for %s: %s", email, master_uuid)
            except identity_client.IdentityEmailAlreadyExists:
                # Fallback to lookup
                logger.info("Email %s already exists in Identity, performing lookup", email)
                result = identity_client.lookup_by_email(email)
                if result and result.get("master_uuid"):
                    master_uuid = result["master_uuid"]
                    logger.info("Found existing master_uuid for %s: %s", email, master_uuid)
                else:
                    logger.error("Identity lookup failed for existing email %s", email)
                    self._update_partner(partner_id, None, "error", "Identity lookup failed for existing email")
                    return

            if master_uuid:
                self._update_partner(partner_id, master_uuid, "linked")
            else:
                self._update_partner(partner_id, None, "error", "No master_uuid returned from Identity")

        except identity_client.IdentityUnavailableError:
            logger.warning("Identity Service unavailable, marking %s as pending", email)
            self._update_partner(partner_id, None, "pending")
        except Exception as e:
            logger.error("Unexpected error linking partner %s: %s", email, e)
            self._update_partner(partner_id, None, "error", str(e))

    def _update_partner(self, partner_id: int, x_user_id: Optional[str], status: str, error_msg: Optional[str] = None):
        vals = {
            "x_identity_status": status,
            "x_identity_last_sync": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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

    def poll(self, interval: int = 10):
        logger.info("Partner Identity Poller started (interval: %ds)", interval)
        while True:
            try:
                partners = self._get_unlinked_partners()
                if partners:
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
