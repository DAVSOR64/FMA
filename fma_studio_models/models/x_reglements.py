# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Real model replacing the Odoo Studio "manual" model x_reglements
(staging DB, audited 2026-07-02). See STUDIO_AUDIT.md at the repo root --
this model only has a name/libelle/sequence skeleton in Studio, no amount,
date or payment-related field was ever added to it.
"""
from odoo import fields, models


class XReglements(models.Model):
    _name = "x_reglements"
    _description = "Règlements"
    _order = "x_studio_sequence, id"

    x_active = fields.Boolean(string="Actif", default=True)
    x_name = fields.Char(string="Description", required=True)
    x_studio_libelle = fields.Char(string="Libelle")
    x_studio_sequence = fields.Integer(string="Séquence")
