# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    fma_acheteur_defaut_id = fields.Many2one(
        "res.users",
        string="Acheteur par défaut",
        help="Responsable porte sur tout bon d'achat qui n'en a pas. "
        "L'approvisionnement cree ses bons SANS acheteur — ils arrivent donc "
        "dans aucune liste « Mes commandes », et personne ne se sent "
        "concerne. Odoo, lui, met l'utilisateur qui saisit : sur un bon ne "
        "d'un automatisme, c'est au mieux arbitraire.",
    )
