# -*- coding: utf-8 -*-
from odoo import fields, models

from .constants import FMA_CATEGORIES_APPRO


class ProductCategory(models.Model):
    """Catégorie de produit : c'est là que vit réellement l'information.

    Le référentiel product.family alimente categ_id via le triplet, mais tous
    les articles n'ont pas de triplet renseigné : les articles achetés portent
    leur catégorie (« All / 01_PROFILS_BARRES_TOLES », « All / 02_REMPLISSAGE »)
    sans forcément avoir de famille. C'est aussi la catégorie que regarde déjà
    fma_custom pour identifier le vitrage.
    """

    _inherit = 'product.category'

    fma_famille_appro = fields.Selection(
        FMA_CATEGORIES_APPRO,
        string="Famille d'approvisionnement (FMA)",
        index=True,
        help="Famille utilisée pour ventiler les dates d'arrivée et les "
             "statuts de réception sur l'ordre de fabrication. Une catégorie "
             "sans valeur hérite de sa catégorie parente.",
    )

    def write(self, vals):
        result = super().write(vals)
        if 'fma_famille_appro' in vals:
            self.env['mrp.production']._fma_marquer_recalcul(
                self.env['mrp.production']._fma_champs_appro()
            )
        return result
