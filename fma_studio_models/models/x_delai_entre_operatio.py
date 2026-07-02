# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Real models replacing the Odoo Studio "manual" models
x_delai_entre_operatio, its line model and its tag model (staging DB,
audited 2026-07-02). See STUDIO_AUDIT.md at the repo root.
"""
from odoo import fields, models


class XDelaiEntreOperatioTag(models.Model):
    _name = "x_delai_entre_operatio_tag"
    _description = "Délai entre opérations Tag"

    x_name = fields.Char(string="Nom", required=True)
    x_color = fields.Integer(string="Couleur")


class XDelaiEntreOperatio(models.Model):
    _name = "x_delai_entre_operatio"
    _description = "Délai entre opérations"
    _order = "x_studio_sequence, id"

    x_active = fields.Boolean(string="Actif", default=True)
    x_name = fields.Char(string="Description", required=True)
    x_studio_char_field_3op_1iv4qb7ld = fields.Char(string="Nouveau Texte")
    x_studio_dlai_entre_oprations = fields.Integer(string="Délai entre opérations")
    x_studio_poste_bloquant_1 = fields.Many2one("mrp.workcenter", string="Poste bloquant 1")
    x_studio_poste_bloquant_2 = fields.Many2one("mrp.workcenter", string="Poste bloquant 2")
    x_studio_poste_de_travail_deb = fields.Many2one("mrp.workcenter", string="Poste de travail deb")
    x_studio_poste_de_travail_fin = fields.Many2one("mrp.workcenter", string="Poste de travail fin")
    x_studio_sequence = fields.Integer(string="Séquence")
    x_studio_tag_ids = fields.Many2many("x_delai_entre_operatio_tag", string="Étiquettes")
    x_delai_entre_operatio_line_ids_42f81 = fields.One2many(
        "x_delai_entre_operatio_line_07ffc", "x_delai_entre_operatio_id", string="Nouvelles lignes"
    )


class XDelaiEntreOperatioLine(models.Model):
    _name = "x_delai_entre_operatio_line_07ffc"
    _description = "Délai entre opérations Line"

    x_delai_entre_operatio_id = fields.Many2one("x_delai_entre_operatio", string="Délai entre opérations")
    x_name = fields.Char(string="Description", required=True)
    x_studio_sequence = fields.Integer(string="Séquence")
