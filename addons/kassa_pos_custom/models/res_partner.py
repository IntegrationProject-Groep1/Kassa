# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    """Extends res.partner with all Kassa-specific custom fields.

    These fields are the single source of truth for the integration layer:
    the Python services (receiver.py, order_poller.py, partner_identity_poller.py)
    read and write them via XML-RPC, and the POS frontend reads them from the
    session loader payload (see PosSession._loader_params_res_partner).

    Field groups and their owners
    ─────────────────────────────
    Identity / CRM linkage (written by receiver.py on new_registration):
      x_user_id            — master_uuid from the central Identity Service; the
                             canonical cross-system identifier for this person.
      x_badge_id           — physical RFID badge or QR code identifier, set when
                             a badge_assigned message arrives from the IoT team.
      x_badge_sent         — True once badge_assigned has been published to RabbitMQ,
                             preventing the poller from sending it twice.
      x_identity_status    — tracks whether the partner has been linked to the
                             Identity Service (pending / linked / error).
      x_identity_last_sync — timestamp of the most recent identity-link attempt,
                             used by the error-cooldown logic in partner_identity_poller.py.

    Payment / registration (written by receiver.py on new_registration / profile_update):
      x_outstanding_amount — total amount the visitor still owes for their sessions.
      x_payment_status     — human-readable status: "unpaid", "paid", or "cancelled".
      x_session_title      — JSON-encoded list of session dicts the visitor is
                             registered for: [{"session_id": "...", "title": "...", "price": ...}].
                             Stored as Char because Odoo custom fields do not support arrays.
      x_date_of_birth      — date of birth, used for age-restricted product checks.
      x_rabbitmq_error     — last integration error logged to this partner record
                             (written by receiver.py on processing failure, and by
                             partner_identity_poller.py on identity-link error).

    Wallet lease lifecycle (written by receiver.py during badge/QR scan flow):
      x_wallet_balance          — leased balance; Kassa is the source of truth
                                  while x_lease_active=True. Must not be modified
                                  directly — use action_add_wallet_amount() or
                                  action_process_wallet_payment() for atomicity.
      x_pending_topup_balance   — top-ups received after badge scan but before
                                  wallet_lease_grant arrives from CRM. Merged into
                                  x_wallet_balance by process_wallet_lease_grant().
      x_lease_active            — True between wallet_lease_request (badge scan) and
                                  wallet_lease_return (checkout / event end).
      x_lease_id                — lease identifier returned by CRM in wallet_lease_grant;
                                  empty string while the grant is still in-flight.
      x_lease_transaction_count — count of wallet transactions during this lease,
                                  incremented atomically by action_increment_lease_tx_count().
    """
    _inherit = 'res.partner'

    x_user_id = fields.Char(string="External CRM User ID", index=True)
    x_badge_id = fields.Char(string="IoT Badge ID", index=True)
    x_badge_sent = fields.Boolean(string="Badge Assignment Sent to CRM")
    x_wallet_balance = fields.Float(string="Visitor Wallet Balance")
    x_pending_topup_balance = fields.Float(string="Pending Top-up (pre-lease)")
    x_date_of_birth = fields.Date(string="Date of Birth")
    x_session_id = fields.Char(string="Session ID")
    x_session_title = fields.Char(string="Session Title")
    x_outstanding_amount = fields.Float(string="Outstanding Amount")
    x_payment_status = fields.Char(string="Payment Status")
    x_rabbitmq_error = fields.Text(string="RabbitMQ Integration Error")
    x_lease_active = fields.Boolean(string="Wallet Lease Active")
    x_lease_id = fields.Char(string="Wallet Lease ID")
    x_lease_transaction_count = fields.Integer(string="Lease Transaction Count")
    x_identity_status = fields.Selection(
        selection=[('pending', 'Pending'), ('linked', 'Linked'), ('error', 'Error')],
        string="Identity Linking Status",
    )
    x_identity_last_sync = fields.Datetime(string="Last Identity Sync")
