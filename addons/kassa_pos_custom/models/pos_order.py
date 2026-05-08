# -*- coding: utf-8 -*-
from odoo import models, api


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

    @api.model
    def action_process_wallet_payment(self, order_id, partner_id, amount_deducted):
        """
        Atomically deducts the wallet balance from the partner and marks the order as processed.
        Executed in a single PostgreSQL transaction by the Odoo ORM.
        """
        order = self.browse(order_id)
        if not order.exists():
            raise ValueError(f"Order {order_id} does not exist.")

        # If already flagged, return current balance immediately (idempotency check)
        if order.x_wallet_updated:
            partner = self.env['res.partner'].browse(partner_id)
            return round(float(partner.x_wallet_balance or 0.0), 2)

        partner = self.env['res.partner'].browse(partner_id)
        if not partner.exists():
            raise ValueError(f"Partner {partner_id} does not exist.")

        current_balance = partner.x_wallet_balance or 0.0
        new_balance = round(float(current_balance) - float(amount_deducted), 2)

        # Write both updates inside this single transaction
        partner.write({'x_wallet_balance': new_balance})
        order.write({'x_wallet_updated': True})

        return new_balance

    @api.model
    def action_add_wallet_amount(self, partner_id, delta):
        """
        Atomically adds delta to the partner's x_wallet_balance.

        Runs inside a single PostgreSQL transaction, preventing the
        read-modify-write race between the order poller and the receiver
        (e.g. a remote top-up arriving while a bar purchase is being processed).
        Pass a negative delta to deduct.
        """
        partner = self.env['res.partner'].browse(partner_id)
        if not partner.exists():
            raise ValueError(f"Partner {partner_id} does not exist.")
        new_balance = round(float(partner.x_wallet_balance or 0.0) + float(delta), 2)
        partner.write({'x_wallet_balance': new_balance})
        return new_balance

    @api.model
    def send_partner_bus_event(
        self, partner_id: int, outstanding_amount: float,
        payment_status: str, name: str,
    ) -> bool:
        """
        Publish a kassa_partner_update event on the Odoo long-polling bus.

        Called by the external integration service (receiver.py and
        order_poller.py) via XML-RPC.  In Odoo 17 the bus.bus._sendone
        method is private and cannot be invoked from outside; this public
        wrapper bridges that gap without any privilege escalation — it runs
        under the same uid used for all other XML-RPC calls.

        Returns True so callers can distinguish success from an exception.
        """
        # Odoo 17 _sendone signature: (target, notification_type, message)
        # target is the channel name string for broadcast events.
        self.env['bus.bus']._sendone(
            'kassa_partner_update',
            'kassa_partner_update',
            {
                'partner_id': partner_id,
                'x_outstanding_amount': outstanding_amount,
                'x_payment_status': payment_status,
                'name': name,
            },
        )
        return True
