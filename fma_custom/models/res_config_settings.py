# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    fma_acheteur_defaut_id = fields.Many2one(
        related="company_id.fma_acheteur_defaut_id",
        string="Acheteur par défaut",
        readonly=False,
    )
