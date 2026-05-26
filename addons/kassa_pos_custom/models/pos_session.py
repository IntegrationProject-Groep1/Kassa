# -*- coding: utf-8 -*-
import logging

from odoo import models, SUPERUSER_ID
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

    def _loader_params_product_product(self):
        """Add x_session_id to product data sent to the POS frontend.

        x_session_id is the stable Planning identifier on session products.
        The POS JS uses it as the primary key in _kassaIsSessionProduct() to
        reliably detect session products without depending on category names.
        """
        result = super()._loader_params_product_product()
        search_params = result.get('search_params', {})
        fields = search_params.get('fields', [])
        if 'x_session_id' not in fields:
            fields.append('x_session_id')
        return result

    def kassa_notify_product_update(self, product_ids=None):
        """Push updated product catalogue to every open POS session via the bus.

        Called via XML-RPC by the integration service after new session products
        are created or updated.  The caller may pass *product_ids* (a list of
        product.product ids) to guarantee the bus notification fires even when no
        open POS sessions are found — e.g. if the session search fails due to a
        company-context mismatch.

        Returns the number of POS sessions notified via _notify.
        """
        # Use a superuser environment to bypass any allowed_company_ids restriction
        # from the calling context. When invoked via XML-RPC from receiver.py, the
        # integration user's company context persists through sudo() in Odoo 17 and
        # silently excludes POS sessions from other companies.
        super_env = self.env(user=SUPERUSER_ID)
        open_sessions = super_env['pos.session'].search(
            [('state', 'in', ('opened', 'opening_control'))]
        )

        notified = 0
        all_product_ids = list(product_ids or [])

        if not open_sessions:
            _logger.info("[KASSA] kassa_notify_product_update: no open POS sessions found")
        else:
            for config in open_sessions.mapped('config_id'):
                sessions_in_config = open_sessions.filtered(lambda s: s.config_id == config)
                params = sessions_in_config[0]._loader_params_product_product()
                search_params = params.get('search_params', {})
                domain = search_params.get('domain', [])
                if config.company_id:
                    domain = expression.AND([domain, [('company_id', 'in', (config.company_id.id, False))]])
                products = (
                    super_env['product.product']
                    .search_read(
                        domain,
                        fields=search_params.get('fields', []),
                        limit=search_params.get('limit', False),
                        order=search_params.get('order', False),
                    )
                )
                all_product_ids.extend(p['id'] for p in products)
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
