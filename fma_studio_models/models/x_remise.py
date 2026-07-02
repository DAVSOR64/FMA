# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Real models replacing the Odoo Studio "manual" models of the "remise"
family: x_remise, x_remises, x_remise_affaire, x_remises_affaire,
x_remise_chantier and its two line models (staging DB, audited 2026-07-02).
See STUDIO_AUDIT.md at the repo root.

NOTE: none of these models has an actual discount amount/percentage field --
only name/sequence/contact skeletons, and x_remise_affaire.x_studio_libelle /
x_remises_affaire.x_studio_libelle are many2one fields pointing back at
their OWN model (self-reference), which is almost certainly a Studio
mis-configuration rather than an intentional design. Kept as-is (schema
ported faithfully, not redesigned) -- confirm with the business whether this
whole family is actually used before building any workflow on top of it.
"""
from odoo import fields, models


class XRemise(models.Model):
    _name = "x_remise"
    _description = "Remise"
    _order = "x_studio_sequence, id"

    x_active = fields.Boolean(string="Actif", default=True)
    x_name = fields.Char(string="Description", required=True)
    x_studio_partner_email = fields.Char(string="E-mail")
    x_studio_partner_id = fields.Many2one("res.partner", string="Contact")
    x_studio_partner_phone = fields.Char(string="Téléphone")
    x_studio_sequence = fields.Integer(string="Séquence")


class XRemises(models.Model):
    _name = "x_remises"
    _description = "Remises"
    _order = "x_studio_sequence, id"

    x_active = fields.Boolean(string="Actif", default=True)
    x_name = fields.Char(string="Description", required=True)
    x_studio_sequence = fields.Integer(string="Séquence")


class XRemiseAffaire(models.Model):
    _name = "x_remise_affaire"
    _description = "Remise Affaire"
    _order = "x_studio_sequence, id"

    x_active = fields.Boolean(string="Actif", default=True)
    x_name = fields.Char(string="Description", required=True)
    x_studio_libelle = fields.Many2one("x_remise_affaire", string="libelle")
    x_studio_sequence = fields.Integer(string="Séquence")


class XRemisesAffaire(models.Model):
    _name = "x_remises_affaire"
    _description = "Remises Affaire"
    _order = "x_studio_sequence, id"

    x_active = fields.Boolean(string="Actif", default=True)
    x_name = fields.Char(string="Description", required=True)
    x_studio_libelle = fields.Many2one("x_remises_affaire", string="libelle")
    x_studio_sequence = fields.Integer(string="Séquence")


class XRemiseChantierLine46d7e(models.Model):
    _name = "x_remise_chantier_line_46d7e"
    _description = "Remise Chantier Line (46d7e)"

    x_name = fields.Char(string="Description", required=True)
    x_remise_chantier_id = fields.Many2one("x_remise_chantier", string="Remise Chantier")
    x_studio_sequence = fields.Integer(string="Séquence")


class XRemiseChantierLineDa285(models.Model):
    _name = "x_remise_chantier_line_da285"
    _description = "Remise Chantier Line (da285)"

    x_name = fields.Char(string="Description", required=True)
    x_remise_chantier_id = fields.Many2one("x_remise_chantier", string="Remise Chantier")
    x_studio_sequence = fields.Integer(string="Séquence")


class XRemiseChantier(models.Model):
    _name = "x_remise_chantier"
    _description = "Remise Chantier"
    _order = "x_studio_sequence, id"

    x_active = fields.Boolean(string="Actif", default=True)
    x_name = fields.Char(string="Description", required=True)
    x_studio_libelle = fields.Char(string="libelle")
    x_studio_libelle_1 = fields.Many2one("x_remise_chantier_line_46d7e", string="libelle")
    x_studio_many2one_field_2m5_1invkcoub = fields.Many2one("x_remise_chantier", string="Nouveau Many2One")
    x_studio_sequence = fields.Integer(string="Séquence")
    x_studio_one2many_field_3o8_1invkeis7 = fields.One2many(
        "x_remise_chantier_line_da285", "x_remise_chantier_id", string="Nouvelles lignes"
    )
    x_studio_one2many_field_8i9_1invkbjin = fields.One2many(
        "x_remise_chantier_line_46d7e", "x_remise_chantier_id", string="Nouvelles lignes"
    )
