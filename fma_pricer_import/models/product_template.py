# -*- coding: utf-8 -*-
"""Empreinte du produit fabrique, issue du chiffrage."""
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    pricer_signature = fields.Char(
        string="Empreinte chiffrage",
        index=True,
        copy=False,
        help="Empreinte de la definition technique issue du pricer "
        "(designation, dimensions, composants, debit). Deux positions de lots "
        "differents qui portent la meme empreinte sont le meme produit "
        "fabrique : elles ne font qu'une seule ligne de devis.",
    )
