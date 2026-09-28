# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    fma_lot_max_menuiserie = fields.Integer(
        related="company_id.fma_lot_max_menuiserie",
        string="Menuiseries max par lot",
        readonly=False,
    )
    fma_lot_product_debit_id = fields.Many2one(
        related="company_id.fma_lot_product_debit_id",
        string="Article debite par defaut",
        readonly=False,
    )
