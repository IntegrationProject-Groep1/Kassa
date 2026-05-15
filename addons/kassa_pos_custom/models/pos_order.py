# -*- coding: utf-8 -*-
from odoo import models, api
from odoo.tools import float_compare


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
        partner = self.env['res.partner'].browse(partner_id)
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
