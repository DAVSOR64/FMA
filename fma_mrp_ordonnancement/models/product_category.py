# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .constants import FMA_CATEGORIES_APPRO


class ProductCategory(models.Model):
    """La famille d'approvisionnement est une propriété du produit.

    Le classeur devinait la famille depuis le nom du fournisseur, faute de
    mieux. C'était faux : RODENBERG figurait à la fois dans la liste
    « panneaux » et dans la liste « complémentaire », parce qu'un fournisseur
    vend plusieurs familles. La catégorie du produit, elle, est univoque —
    et fma_custom s'en sert déjà pour identifier le vitrage.
    """

    _inherit = 'product.category'

    fma_famille_appro = fields.Selection(
        FMA_CATEGORIES_APPRO,
        string="Famille d'approvisionnement (FMA)",
        index=True,
        help="Famille utilisée pour ventiler les dates d'arrivée et les "
             "statuts de réception sur l'ordre de fabrication.",
    )

    def write(self, vals):
        result = super().write(vals)
        if 'fma_famille_appro' in vals:
            self.env['mrp.production']._fma_marquer_recalcul(
                self.env['mrp.production']._fma_champs_appro()
            )
        return result
