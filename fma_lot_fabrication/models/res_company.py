# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    fma_lot_max_menuiserie = fields.Integer(
        string="Menuiseries max par lot",
        # 8 et non 10 : c'est le nombre que la production tient reellement
        # sur une barre. Le chiffre n'est qu'indicatif — rien n'empeche de
        # composer un lot plus gros — mais il oriente la mise en lot, donc
        # il doit dire vrai.
        default=8,
        help="Plafond du nombre de menuiseries dans un lot de fabrication, "
        "impose par l'optimisation du debit. 0 = pas de limite.",
    )
    fma_lot_product_debit_id = fields.Many2one(
        "product.product",
        string="Article debite par defaut",
        domain="[('type', '=', 'consu')]",
        help="« Debit du lot » : l'article que porte l'OF de debit, pour le "
        "nombre de menuiseries du lot. Generique et NON suivi en stock — les "
        "ensembles debites des menuiseries sortent en sous-produits de "
        "l'ordre, ce sont eux que les OF d'assemblage consomment. Il ne sert "
        "d'article debite qu'aux lots saisis a la main, dont les lignes ne "
        "portent pas leur ensemble debite.",
    )
