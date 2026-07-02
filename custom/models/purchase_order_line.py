# -*- coding: utf-8 -*-
"""Champs migrés depuis Odoo Studio (staging DB, audité 2026-07-02).
Noms techniques conservés à l'identique, aucune migration de données.
3 champs volontairement exclus (voir STUDIO_AUDIT.md) : dimensions non
stockées côté Studio, ou related_field_* (cible non vérifiable).
"""
from odoo import fields, models


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    x_studio_forme = fields.Char(string="Forme", readonly=True)
    x_studio_posit = fields.Char(string="Position/N°")
    x_studio_position = fields.Char(string="position", readonly=True)
    x_studio_spacer = fields.Char(string="spacer")
    x_studio_spacer_2 = fields.Char(string="Spacer", readonly=True)
