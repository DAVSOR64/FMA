# -*- coding: utf-8 -*-
from odoo import fields, models


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    atelier_id = fields.Many2one(
        "fma.atelier",
        string="Atelier (FMA)",
        index=True,
        tracking=True,
        copy=True,
        help=(
            "Atelier métier sur lequel l'OF sera produit. "
            "Ce champ sert au macro-planning et aux restitutions de capacité, "
            "sans créer d'entrepôts ou de transferts logistiques entre ateliers."
        ),
    )
