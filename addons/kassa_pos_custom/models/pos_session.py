# -*- coding: utf-8 -*-
import logging

from odoo import models

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

    def kassa_notify_product_update(self):
        """Push updated product catalogue to every open POS session via the bus.

        Called via XML-RPC by the integration service after new session products
        are created by process_session_view_response, so the POS frontend picks
        up the new products without requiring a manual session reload.

        Returns the number of sessions notified.
        """
        open_sessions = self.env['pos.session'].search([('state', '=', 'opened')])
        if not open_sessions:
            return 0

        # Fetch the full product list in the format the POS loader expects.
        # We use the first open session's loader params as the template; all
        # sessions in a given POS config share the same product domain.
        params = open_sessions[0]._loader_params_product_product()
        search_params = params.get('search_params', {})
        products = self.env['product.product'].search_read(
            search_params.get('domain', []),
            fields=search_params.get('fields', []),
            limit=search_params.get('limit', False),
            order=search_params.get('order', False),
        )

        notified = 0
        for session in open_sessions:
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
