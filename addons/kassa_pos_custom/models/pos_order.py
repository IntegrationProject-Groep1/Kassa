# -*- coding: utf-8 -*-
import logging

from odoo import fields, models, api
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    """
    Extensions to pos.order for the Kassa integration.

    Provides two public XML-RPC methods called by the external integration
    service (receiver.py / order_poller.py):

    - action_process_wallet_payment: atomically deducts a Badge Wallet payment.
    - send_partner_bus_event: publishes a kassa_partner_update bus event so the
      POS frontend updates in real time without a session restart (Story 21).

    Both are @api.model so they are called without a record context:
        models.execute_kw(db, uid, pwd, 'pos.order', '<method>', [args...])
    """

    _inherit = 'pos.order'

    x_rabbitmq_sent = fields.Boolean(string="Sent to CRM via RabbitMQ")
    x_wallet_updated = fields.Boolean(string="Wallet Balance Adjusted")
    x_payment_message_id = fields.Char(string="CRM Payment Correlation ID")
    x_invoice_message_id = fields.Char(string="Invoice Request Message ID")
    x_rabbitmq_error = fields.Text(string="RabbitMQ Integration Error")

    @api.model
    def action_process_wallet_payment(self, order_id, partner_id, amount_deducted):
        """
        Atomically deducts the wallet balance from the partner and marks the order as processed.
        Executed in a single PostgreSQL transaction by the Odoo ORM.
        """
        order = self.sudo().browse(order_id)
        if not order.exists():
            raise ValueError(f"Order {order_id} does not exist.")

        # If already flagged, return current balance immediately (idempotency check)
        if order.x_wallet_updated:
            partner = self.env['res.partner'].sudo().browse(partner_id)
            return round(float(partner.x_wallet_balance or 0.0), 2)

        partner = self.env['res.partner'].sudo().browse(partner_id)
        if not partner.exists():
            raise ValueError(f"Partner {partner_id} does not exist.")

        # Lock the row and check balance before deducting (prevents overdraft)
        self.env.cr.execute(
            "SELECT COALESCE(x_wallet_balance, 0.0) FROM res_partner WHERE id = %s FOR UPDATE",
            (partner_id,)
        )
        lock_row = self.env.cr.fetchone()
        if lock_row is None:
            raise ValueError(f"Partner {partner_id} was deleted during balance check.")
        current_balance = float(lock_row[0])
        if float_compare(current_balance, float(amount_deducted), precision_digits=2) == -1:
            raise ValueError(
                f"Insufficient wallet balance for partner {partner_id}: "
                f"balance=€{current_balance:.2f}, required=€{amount_deducted:.2f}"
            )

        # Atomic deduction via direct SQL UPDATE
        self.env.cr.execute(
            "UPDATE res_partner "
            "SET x_wallet_balance = ROUND((COALESCE(x_wallet_balance, 0) - %s)::numeric, 2) "
            "WHERE id = %s RETURNING x_wallet_balance",
            (float(amount_deducted), partner_id),
        )
        row = self.env.cr.fetchone()
        if row is None:
            raise ValueError(f"Partner {partner_id} was deleted during balance update.")
        new_balance = row[0]

        # Flag the order as updated and invalidate the partner cache
        order.write({'x_wallet_updated': True})
        partner.invalidate_recordset(['x_wallet_balance'])

        return float(new_balance)

    @api.model
    def action_add_wallet_amount(self, partner_id, delta):
        """
        Atomically adds delta to the partner's x_wallet_balance.

        Runs inside a single PostgreSQL transaction, preventing the
        read-modify-write race between the order poller and the receiver
        (e.g. a remote top-up arriving while a bar purchase is being processed).
        Pass a negative delta to deduct.
        """
        partner = self.env['res.partner'].sudo().browse(partner_id)
        if not partner.exists():
            raise ValueError(f"Partner {partner_id} does not exist.")
        self.env.cr.execute(
            "UPDATE res_partner "
            "SET x_wallet_balance = ROUND((COALESCE(x_wallet_balance, 0) + %s)::numeric, 2) "
            "WHERE id = %s RETURNING x_wallet_balance",
            (float(delta), partner_id),
        )
        row = self.env.cr.fetchone()
        if row is None:
            raise ValueError(f"Partner {partner_id} was deleted during balance update.")
        new_balance = row[0]
        partner.invalidate_recordset(['x_wallet_balance'])
        return float(new_balance)

    @api.model
    def action_increment_lease_tx_count(self, partner_id):
        """
        Atomically increments x_lease_transaction_count by 1.

        Called by order_poller after each successful consumption/top-up/refund
        while a lease is active.  Using a direct SQL UPDATE avoids the
        read-modify-write race between the poller and receiver threads.
        """
        self.env.cr.execute(
            "UPDATE res_partner "
            "SET x_lease_transaction_count = COALESCE(x_lease_transaction_count, 0) + 1 "
            "WHERE id = %s RETURNING x_lease_transaction_count",
            (partner_id,),
        )
        row = self.env.cr.fetchone()
        return row[0] if row else 0

    @api.model
    def send_partner_bus_event(
        self, partner_id: int, outstanding_amount: float,
        payment_status: str, name: str,
    ) -> bool:
        """
        Publish a KASSA_PARTNER_UPDATE notification to all open POS sessions.

        In Odoo 17, bus.bus._sendone() with a plain string channel requires the
        client to subscribe via addChannel(), which Odoo 17's bus security model
        silently rejects for non-whitelisted channels.  Using session._notify()
        instead sends through the POS session's own authorized WebSocket channel
        ('pos.session', session_id) that the browser is already subscribed to —
        the same pattern used by kassa_notify_product_update() for products.

        Returns True so callers can distinguish success from an exception.
        """
        payload = {
            'partner_id': partner_id,
            'x_outstanding_amount': outstanding_amount,
            'x_payment_status': payment_status,
            'name': name,
        }
        open_sessions = (
            self.env['pos.session']
            .sudo()
            .search([('state', 'in', ('opened', 'opening_control'))])
        )
        for session in open_sessions:
            try:
                session._kassa_bus_notify('KASSA_PARTNER_UPDATE', payload)
            except Exception as exc:
                _logger.warning(
                    "[Kassa] Could not notify POS session %s: %s", session.name, exc
                )
        return True
