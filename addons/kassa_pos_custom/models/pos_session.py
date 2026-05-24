# -*- coding: utf-8 -*-
import logging

from odoo import models
from odoo.osv import expression

_logger = logging.getLogger(__name__)


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
        """Add Kassa custom fields to the partner payload sent to the POS frontend.

        Also widens the search domain so all Kassa event attendees (x_user_id set)
        are loaded regardless of customer_rank. The base Odoo domain filters by
        customer_rank > 0, which excludes partners created before customer_rank=1
        was set on new_registration. The OR ensures they appear in the customer tab.
        """
        result = super()._loader_params_res_partner()
        extra = [
            'x_outstanding_amount',
            'x_payment_status',
            'x_session_title',
            'x_wallet_balance',
            'x_user_id',
            'x_badge_id',
            'x_lease_active',
            'x_lease_id',
            'vat',
        ]
        search_params = result.get('search_params', {})
        fields = search_params.get('fields', [])
        for f in extra:
            if f not in fields:
                fields.append(f)

        search_params['domain'] = expression.OR([
            search_params.get('domain', []),
            [('x_user_id', '!=', False)],
        ])
        return result

    def kassa_notify_product_update(self):
        """Push updated product catalogue to every open POS session via the bus.

        Called via XML-RPC by the integration service after new session products
        are created by process_session_view_response, so the POS frontend picks
        up the new products without requiring a manual session reload.

        Each POS config (Bar Kassa, Inschrijvingskassa) has its own product domain,
        so products are fetched separately per config and each session only receives
        the products that belong to its own config.

        Returns the number of sessions notified.
        """
        open_sessions = self.env['pos.session'].sudo().search([('state', 'in', ('opened', 'opening_control'))])
        if not open_sessions:
            return 0

        notified = 0
        for config in open_sessions.mapped('config_id'):
            sessions_in_config = open_sessions.filtered(lambda s: s.config_id == config)
            params = sessions_in_config[0]._loader_params_product_product()
            search_params = params.get('search_params', {})
            domain = search_params.get('domain', [])
            if config.company_id:
                domain = expression.AND([domain, [('company_id', 'in', (config.company_id.id, False))]])
            products = self.env['product.product'].sudo().search_read(
                domain,
                fields=search_params.get('fields', []),
                limit=search_params.get('limit', False),
                order=search_params.get('order', False),
            )
            for session in sessions_in_config:
                try:
                    session._notify('SYNC_PRODUCT_UPDATED', {'product.product': products})
                    notified += 1
                    _logger.info(
                        "[KASSA] Pushed SYNC_PRODUCT_UPDATED to POS session %s (%d products)",
                        session.name, len(products),
                    )
                except Exception as exc:
                    _logger.warning(
                        "[KASSA] Could not notify POS session %s: %s", session.name, exc
                    )

        return notified
