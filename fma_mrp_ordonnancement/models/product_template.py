# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    fma_exclu_reperes = fields.Boolean(
        string="Exclu du comptage des repères",
        help="Coché sur l'éco-participation et sur toute ligne de devis qui ne "
             "correspond pas à une menuiserie, afin qu'elle ne soit pas comptée "
             "dans le nombre de repères de l'ordre de fabrication.",
    )

    def _fma_famille_appro(self):
        """Famille d'approvisionnement effective du produit.

        La sous-famille l'emporte sur la famille : 02_Remplissage porte à la
        fois le vitrage et les panneaux, seul le niveau sous-famille permet de
        les distinguer.
        """
        self.ensure_one()
        return (
            self.subfamily_id.fma_famille_appro
            or self.family_id.fma_famille_appro
            or False
        )
