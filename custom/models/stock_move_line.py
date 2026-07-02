# -*- coding: utf-8 -*-
"""Champs migrés depuis Odoo Studio (staging DB, audité 2026-07-02).
Noms techniques conservés à l'identique, aucune migration de données.
10 champs volontairement exclus (voir STUDIO_AUDIT.md) : related_field_*
(cible non vérifiable) ou non stockés.
"""
from odoo import fields, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    x_studio_many2one_field_5ai0g = fields.Many2one("x_affaire", string="Affaire")
    x_studio_many2one_field_SJp6r = fields.Many2one("x_affaire", string="Affaire")
