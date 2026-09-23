# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    fma_article_libre = fields.Boolean(
        string="Article libre LOGIKAL",
        copy=False,
        index="btree_not_null",
        help="Article ne venant d'aucun catalogue fournisseur : le chiffreur "
        "l'a saisi a la main dans LOGIKAL (ligne « manuelle »). Il n'a donc "
        "pas de reference article, et le connecteur lui en fabrique une, du "
        "type « ABC A26-00-00002_LB1 ».",
    )
