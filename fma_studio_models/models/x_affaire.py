# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Real models replacing the Odoo Studio "manual" models x_affaire,
x_affaire_stage and x_affaire_tag.

Technical names and field names are kept identical to the Studio-generated
ones so that existing data and other modules referencing
env['x_affaire'] (mrp_capacity_planning, sqlite_connector) keep working
unchanged.

NOTE: the exact option values/labels of x_studio_kanban_state could not be
read from ir.model.fields.selection -- they are set here to Odoo's usual
kanban_state triplet (normal/done/blocked) and MUST be verified against the
live data before this module is installed.
"""
from odoo import fields, models


class XAffaireStage(models.Model):
    _name = "x_affaire_stage"
    _description = "Affaire Stage"
    _rec_name = "x_name"
    _order = "x_studio_sequence, id"

    x_name = fields.Char(string="Nom de l'étape", required=True, translate=True)
    x_studio_sequence = fields.Integer(string="Séquence")


class XAffaireTag(models.Model):
    _name = "x_affaire_tag"
    _description = "Affaire Tag"
    _rec_name = "x_name"

    x_name = fields.Char(string="Nom", required=True)
    x_color = fields.Integer(string="Couleur")
    x_studio_ref_affaire = fields.Text(string="Nom affaire")


class XAffaire(models.Model):
    _name = "x_affaire"
    # La chronologie (chatter) était présente côté Studio puis perdue au
    # portage : on rétablit mail.thread/mail.activity.mixin. La position
    # "à droite" est un réglage d'affichage par utilisateur en Odoo 19, pas
    # un attribut de vue.
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Affaire"
    _rec_name = "x_name"
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
        tracking=True,
    )
    x_studio_notes = fields.Html(string="Notes")
    x_studio_partner_email = fields.Char(string="Email")
    x_studio_partner_id = fields.Many2one("res.partner", string="Contact")
    x_studio_partner_phone = fields.Char(string="Téléphone")
    # Commercial (employé) rattaché à l'affaire. FMA/Janneau n'utilise pas le
    # "Commercial" natif d'Odoo (user_id, licence utilisateur) mais un employé
    # -- ce champ n'existait pas côté Studio ; le "Commercial" doit remonter
    # jusqu'à l'Affaire depuis le contact lié. Calculé dans le module
    # `custom`, qui dépend de ce module-ci et peut donc lire
    # res.partner.x_studio_commercial_1.
    x_studio_commercial_id = fields.Many2one("hr.employee", string="Commercial", tracking=True)
    # Mode de règlement (Studio: x_reglements, ex. "11" = Virement Bancaire).
    # Champ distinct de la "Condition de paiement" standard d'Odoo -- existait
    # sur les anciennes affaires (saisi/synchronisé côté Studio), plus sur les
    # nouvelles depuis le portage. Calculé dans le module `custom`, comme
    # x_studio_commercial_id ci-dessus.
    x_studio_mode_de_rglement_id = fields.Many2one("x_reglements", string="Mode de règlement", tracking=True)
    x_studio_priority = fields.Boolean(string="Haute priorité")
    x_studio_sequence = fields.Integer(string="Séquence")
    x_studio_stage_id = fields.Many2one("x_affaire_stage", string="Étape", required=True, tracking=True)
    x_studio_tag_ids = fields.Many2many("x_affaire_tag", string="Étiquettes")
    x_studio_user_id = fields.Many2one("res.users", string="Responsable", tracking=True)
    x_studio_value = fields.Float(string="Valeur")
