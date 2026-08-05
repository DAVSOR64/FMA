# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    fma_lot_max_menuiserie = fields.Integer(
        string="Menuiseries max par lot",
        default=10,
        help="Plafond du nombre de menuiseries dans un lot de fabrication, "
        "impose par l'optimisation du debit. 0 = pas de limite.",
    )
    fma_lot_product_debit_id = fields.Many2one(
        "product.product",
        string="Article debite par defaut",
        domain="[('type', 'in', ('consu', 'product'))]",
        help="Article intermediaire produit par l'OF Debit et consomme par "
        "les OF Assemblage.",
    )
