# -*- coding: utf-8 -*-
from odoo import models, api

class PosOrder(models.Model):
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
