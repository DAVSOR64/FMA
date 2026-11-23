# -*- coding: utf-8 -*-
"""Empreinte du produit fabrique, issue du chiffrage."""
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # Les coupes de CET ensemble debite, tous lots confondus. Le rattachement
    # se fait au modele et non a la variante : un onglet de fiche article vit
    # sur product.template.
    fma_cut_ids = fields.One2many(
        "fma.lot.cut.line",
        "product_debit_tmpl_id",
        string="Coupes",
        readonly=True,
    )

    pricer_signature = fields.Char(
        string="Empreinte chiffrage",
        index=True,
        copy=False,
        help="Empreinte de la definition technique issue du pricer "
        "(designation, dimensions, composants, debit). Deux positions de lots "
        "differents qui portent la meme empreinte sont le meme produit "
        "fabrique : elles ne font qu'une seule ligne de devis.",
    )
