# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Real models replacing the Odoo Studio "manual" models x_affaire,
x_affaire_stage and x_affaire_tag (staging DB, audited 2026-07-02).

Technical names and field names are kept identical to the Studio-generated
ones so that existing data and other modules referencing
env['x_affaire'] (mrp_capacity_planning, sqlite_connector) keep working
unchanged. See STUDIO_AUDIT.md at the repo root.

NOTE: the exact option values/labels of x_studio_kanban_state could not be
read from ir.model.fields.selection (DB unreachable at the time of writing,
see STUDIO_AUDIT.md) -- they are set here to Odoo's usual kanban_state
triplet (normal/done/blocked) and MUST be verified against the live data
before this module is installed.
"""
from odoo import fields, models


class XAffaireStage(models.Model):
    _name = "x_affaire_stage"
    _description = "Affaire Stage"
    _order = "x_studio_sequence, id"

    x_name = fields.Char(string="Nom de l'étape", required=True)
    x_studio_sequence = fields.Integer(string="Séquence")


class XAffaireTag(models.Model):
    _name = "x_affaire_tag"
    _description = "Affaire Tag"

    x_name = fields.Char(string="Nom", required=True)
    x_color = fields.Integer(string="Couleur")
    x_studio_ref_affaire = fields.Text(string="Nom affaire")


class XAffaire(models.Model):
    _name = "x_affaire"
    _description = "Affaire"
    _order = "x_studio_sequence, id"

    x_active = fields.Boolean(string="Actif", default=True)
    x_color = fields.Integer(string="Couleur")
    x_name = fields.Char(string="Name")
    x_studio_currency_id = fields.Many2one("res.currency", string="Devise")
    x_studio_date = fields.Date(string="Date")
    x_studio_date_start = fields.Datetime(string="Date de début")
    x_studio_date_stop = fields.Datetime(string="Date de fin")
    x_studio_kanban_state = fields.Selection(
        [("normal", "En cours"), ("done", "Prêt"), ("blocked", "Bloqué")],
        string="État kanban",
    )
    x_studio_notes = fields.Html(string="Notes")
    x_studio_partner_email = fields.Char(string="Email")
    x_studio_partner_id = fields.Many2one("res.partner", string="Contact")
    x_studio_partner_phone = fields.Char(string="Téléphone")
    x_studio_priority = fields.Boolean(string="Haute priorité")
    x_studio_sequence = fields.Integer(string="Séquence")
    x_studio_stage_id = fields.Many2one("x_affaire_stage", string="Étape", required=True)
    x_studio_tag_ids = fields.Many2many("x_affaire_tag", string="Étiquettes")
    x_studio_user_id = fields.Many2one("res.users", string="Responsable")
    x_studio_value = fields.Float(string="Valeur")
