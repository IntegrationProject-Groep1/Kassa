# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
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
