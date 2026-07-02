# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Real models replacing the Odoo Studio "manual" models x_gamme_mtn and
x_serie_mtn (staging DB, audited 2026-07-02). See STUDIO_AUDIT.md at the
repo root -- both models only have a name/sequence skeleton in Studio, no
other business field was ever added to them.
"""
from odoo import fields, models


class XGammeMtn(models.Model):
    _name = "x_gamme_mtn"
    _description = "Gamme mtn"
    _order = "x_studio_sequence, id"

    x_active = fields.Boolean(string="Actif", default=True)
    x_name = fields.Char(string="Description", required=True)
    x_studio_sequence = fields.Integer(string="Séquence")


class XSerieMtn(models.Model):
    _name = "x_serie_mtn"
    _description = "Série mtn"
    _order = "x_studio_sequence, id"

    x_active = fields.Boolean(string="Actif", default=True)
    x_name = fields.Char(string="Description", required=True)
    x_studio_gamme_de_la_srie = fields.Many2one("x_gamme_mtn", string="Gamme de la série")
    x_studio_sequence = fields.Integer(string="Séquence")
