# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    x_session_id = fields.Char(string="Planning Session ID", index=True)
    x_is_topup = fields.Boolean(string="Top-up Product")
    x_age_restricted = fields.Boolean(string="Age Restricted")
