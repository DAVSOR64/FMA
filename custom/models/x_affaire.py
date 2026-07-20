# -*- coding: utf-8 -*-
from odoo import api, fields, models


class XAffaire(models.Model):
    _inherit = "x_affaire"

    x_studio_commercial_id = fields.Many2one(
        "hr.employee",
        string="Commercial",
        compute="_compute_x_studio_commercial_id",
        store=True,
        tracking=True,
    )

    @api.depends("x_studio_partner_id")
    def _compute_x_studio_commercial_id(self):
        for affaire in self:
            affaire.x_studio_commercial_id = affaire.x_studio_partner_id.x_studio_commercial_1

    x_studio_mode_de_rglement_id = fields.Many2one(
        "x_reglements",
        string="Mode de règlement",
        compute="_compute_x_studio_mode_de_rglement_id",
        store=True,
        tracking=True,
    )

    @api.depends("x_studio_partner_id")
    def _compute_x_studio_mode_de_rglement_id(self):
        for affaire in self:
            affaire.x_studio_mode_de_rglement_id = affaire.x_studio_partner_id.x_studio_mode_de_rglement_dsa
