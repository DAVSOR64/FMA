# -*- coding: utf-8 -*-
"""Champs migrés depuis Odoo Studio (staging DB, audité 2026-07-02).
Noms techniques conservés à l'identique, aucune migration de données.
6 champs volontairement exclus (voir STUDIO_AUDIT.md) : dimensions non
stockées côté Studio, ou related_field_* (cible non vérifiable).
"""
from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    x_studio_date_livraison_prvue = fields.Datetime(string="Date Livraison prévue", readonly=True)
    x_studio_many2many_field_w5Rtg = fields.Many2many("sale.order", string="Bon de commande")
    x_studio_many2one_field_COPwF = fields.Many2one("sale.order", string="Bon de commande")
    x_studio_position = fields.Char(string="Position", readonly=True)
