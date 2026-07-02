# -*- coding: utf-8 -*-
"""Champs migrés depuis Odoo Studio (staging DB, audité 2026-07-02).
Noms techniques conservés à l'identique, aucune migration de données.
4 champs volontairement exclus (voir STUDIO_AUDIT.md) : dimensions non
stockées côté Studio, ou related_field_* (cible non vérifiable).
"""
from odoo import fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    x_studio_emilien = fields.Many2one("product.removal", string="EMILIEN")
    x_studio_many2one_field_45h_1ilm4m7ne = fields.Many2one("product.template", string="Nouveau Many2One")
    x_studio_many2one_field_4fu_1ilm7522u = fields.Many2one("product.template", string="Nouveau Many2One")
    x_studio_many2one_field_t3xv7 = fields.Many2one("account.analytic.account", string="Compte analytique")
    x_studio_repere = fields.Char(string="Repere", readonly=True)
