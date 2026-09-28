# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    fma_semi_fini = fields.Selection(
        [
            ("debit", "Ensemble débité"),
            ("quincaillerie", "Kit quincaillerie"),
        ],
        string="Semi-fini de lot",
        copy=False,
        index=True,
        help="Nature d'un article intermediaire du lot de fabrication. Le lot "
        "s'y fie, et non a la reference de l'article, pour savoir quel ordre "
        "de fabrication generer : un kit quincaillerie present dans la "
        "nomenclature d'une menuiserie declenche un OF de quincaillerie.",
    )
