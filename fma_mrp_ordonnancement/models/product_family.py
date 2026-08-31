# -*- coding: utf-8 -*-
from odoo import fields, models

from .constants import FMA_CATEGORIES_APPRO

AIDE = (
    "Famille d'approvisionnement FMA, utilisée pour ventiler les dates "
    "d'arrivée et les statuts de réception sur l'ordre de fabrication."
)


class ProductFamily(models.Model):
    """Le référentiel famille pilote déjà la catégorie du produit.

    product_subfamily applique le triplet famille / sous-famille /
    sous-sous-famille sur categ_id. La famille est donc la source, la
    catégorie une conséquence : c'est ici qu'il faut porter l'information.
    """

    _inherit = 'product.family'

    fma_famille_appro = fields.Selection(
        FMA_CATEGORIES_APPRO,
        string="Famille d'approvisionnement (FMA)",
        index=True,
        help=AIDE + " Peut être affinée sous-famille par sous-famille.",
    )

    def write(self, vals):
        result = super().write(vals)
        if 'fma_famille_appro' in vals:
            self.env['purchase.order.line']._fma_recalculer_familles()
            self.env['mrp.production']._fma_marquer_recalcul(
                self.env['mrp.production']._fma_champs_appro()
            )
        return result


class ProductSubFamily(models.Model):
    """Affinage au niveau sous-famille.

    Nécessaire parce qu'une famille ne correspond pas toujours à une seule
    famille d'approvisionnement : 02_Remplissage regroupe le vitrage et les
    panneaux, que le classeur suivait dans deux colonnes distinctes. La valeur
    portée ici l'emporte sur celle de la famille.
    """

    _inherit = 'product.subfamily'

    fma_famille_appro = fields.Selection(
        FMA_CATEGORIES_APPRO,
        string="Famille d'approvisionnement (FMA)",
        index=True,
        help=AIDE + " Laisser vide pour hériter de la famille.",
    )

    def write(self, vals):
        result = super().write(vals)
        if 'fma_famille_appro' in vals:
            self.env['purchase.order.line']._fma_recalculer_familles()
            self.env['mrp.production']._fma_marquer_recalcul(
                self.env['mrp.production']._fma_champs_appro()
            )
        return result
