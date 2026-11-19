# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    fma_acheteur_defaut_id = fields.Many2one(
        related="company_id.fma_acheteur_defaut_id",
        string="Acheteur par défaut",
        readonly=False,
    )
    fma_acheteur_fma_id = fields.Many2one(
        related="company_id.fma_acheteur_fma_id",
        string="Acheteur des affaires FMA",
        readonly=False,
    )
    fma_acheteur_f2m_id = fields.Many2one(
        related="company_id.fma_acheteur_f2m_id",
        string="Acheteur des affaires F2M",
        readonly=False,
    )
