# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    """Extends product.template with Kassa-specific classification fields.

    x_session_id
        Stable external identifier assigned by the Planning/Frontend system.
        Used as the primary lookup key in receiver._ensure_session_product() so
        that product records survive session title renames without creating
        duplicates.  Indexed for fast search_read queries during badge scans.

    x_is_topup
        True for wallet top-up products (e.g. "Top-up EUR 10").  The order poller
        checks this flag via is_topup_product() to detect top-up lines in a POS
        order and trigger the wallet balance update flow instead of the normal
        consumption flow.  The flag is faster than a category name string match
        and survives category renames.

    x_age_restricted
        True for products that require age verification (e.g. Beer).
        Reserved for future enforcement at the POS — not yet used in business
        logic but exposed here so the cashier UI can read it without an extra RPC.
    """
    _inherit = 'product.template'

    x_session_id = fields.Char(string="Planning Session ID", index=True)
    x_is_topup = fields.Boolean(string="Top-up Product")
    x_age_restricted = fields.Boolean(string="Age Restricted")
