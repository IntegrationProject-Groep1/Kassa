# -*- coding: utf-8 -*-
from odoo import models


class PosSession(models.Model):
    """
    Extends pos.session to include Kassa custom fields in the POS session loader.

    When the POS frontend opens a session it bulk-loads all res.partner records
    via _loader_params_res_partner. This override adds the five Kassa-specific
    fields so that outstanding-amount badges and wallet balances are immediately
    available in the partner list without extra RPC calls.
    """

    _inherit = 'pos.session'

    def _loader_params_res_partner(self):
        """Add Kassa custom fields to the partner payload sent to the POS frontend."""
        result = super()._loader_params_res_partner()
        extra = [
            'x_outstanding_amount',
            'x_payment_status',
            'x_wallet_balance',
            'x_user_id',
            'x_badge_id',
        ]
        fields = result.get('search_params', {}).get('fields', [])
        for f in extra:
            if f not in fields:
                fields.append(f)
        return result
