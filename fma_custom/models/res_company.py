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

    # L'ACHETEUR DEPEND DE L'ATELIER, et les deux ateliers vivent dans la
    # MEME societe : le defaut ci-dessus ne peut donc pas les departager.
    # C'est l'etiquette commerciale de l'affaire qui tranche — la meme regle
    # que l'entrepot et l'atelier de fabrication.
    fma_acheteur_fma_id = fields.Many2one(
        "res.users",
        string="Acheteur des affaires FMA",
        help="Responsable porte sur les bons d'achat nes de "
        "l'approvisionnement d'une affaire etiquetee FMA. A defaut, "
        "l'acheteur par defaut ci-dessus s'applique.",
    )
    fma_acheteur_f2m_id = fields.Many2one(
        "res.users",
        string="Acheteur des affaires F2M",
        help="Responsable porte sur les bons d'achat nes de "
        "l'approvisionnement d'une affaire etiquetee F2M. A defaut, "
        "l'acheteur par defaut ci-dessus s'applique.",
    )
