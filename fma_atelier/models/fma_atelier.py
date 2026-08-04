# -*- coding: utf-8 -*-
from odoo import api, fields, models


class FmaAtelier(models.Model):
    _name = "fma.atelier"
    _description = "Atelier de production"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, name"

    name = fields.Char(
        string="Nom",
        required=True,
        tracking=True,
    )
    code = fields.Char(
        string="Code",
        tracking=True,
        help="Code court utilisé pour les filtres, exports et restitutions.",
    )
    sequence = fields.Integer(
        string="Séquence",
        default=10,
    )
    active = fields.Boolean(
        string="Actif",
        default=True,
        tracking=True,
    )
    color = fields.Integer(
        string="Couleur",
        default=0,
    )
    calendar_id = fields.Many2one(
        "resource.calendar",
        string="Calendrier atelier",
        help=(
            "Calendrier optionnel de l'atelier. "
            "Il ne remplace pas les calendriers employés ni les postes de charge. "
            "Il sert uniquement si les modules de capacité souhaitent s'appuyer dessus."
        ),
    )
    company_id = fields.Many2one(
        "res.company",
        string="Société",
        default=lambda self: self.env.company,
        index=True,
    )
    production_count = fields.Integer(
        string="Nombre d'OF",
        compute="_compute_production_count",
    )
    note = fields.Text(
        string="Notes",
    )

    _sql_constraints = [
        (
            "code_company_uniq",
            "unique(code, company_id)",
            "Le code atelier doit être unique par société.",
        ),
    ]

    @api.depends("name")
    def _compute_production_count(self):
        production_model = self.env["mrp.production"]
        for atelier in self:
            atelier.production_count = production_model.search_count([
                ("atelier_id", "=", atelier.id)
            ])

    def action_view_productions(self):
        self.ensure_one()
        action = self.env.ref("mrp.mrp_production_action").read()[0]
        action["domain"] = [("atelier_id", "=", self.id)]
        action["context"] = {
            "default_atelier_id": self.id,
            "search_default_atelier_id": self.id,
        }
        return action
