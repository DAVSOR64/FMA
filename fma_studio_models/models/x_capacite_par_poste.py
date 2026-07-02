# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Real models replacing the Odoo Studio "manual" models x_capacite_par_poste
and x_capacite_par_poste_tag (staging DB, audited 2026-07-02).

Field names are kept identical to the Studio-generated ones: they are read
directly by mrp_capacity_planning/models/mrp_production.py
(env['x_capacite_par_poste'].search([('x_studio_poste', '=', ...)])) which
must keep working unchanged. See STUDIO_AUDIT.md at the repo root.
"""
from odoo import fields, models


class XCapaciteParPosteTag(models.Model):
    _name = "x_capacite_par_poste_tag"
    _description = "Capacité par poste Tag"

    x_name = fields.Char(string="Nom", required=True)
    x_color = fields.Integer(string="Couleur")


class XCapaciteParPoste(models.Model):
    _name = "x_capacite_par_poste"
    _description = "Capacité par poste"
    _order = "x_studio_sequence, id"

    x_active = fields.Boolean(string="Actif", default=True)
    x_name = fields.Char(string="Description", required=True)
    x_studio_dure_max = fields.Integer(string="Durée Max")
    x_studio_dure_min = fields.Integer(string="Durée Min")
    x_studio_nbre_ressources = fields.Integer(string="Nbre Ressources")
    x_studio_poste = fields.Many2one("mrp.workcenter", string="Poste")
    x_studio_sequence = fields.Integer(string="Séquence")
    x_studio_tag_ids = fields.Many2many("x_capacite_par_poste_tag", string="Étiquettes")
