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

        Trois niveaux, du plus précis au plus général :

        1. la sous-famille, seul niveau capable de séparer le vitrage des
           panneaux à l'intérieur de 02_Remplissage ;
        2. la famille ;
        3. la catégorie du produit, en remontant les parents.

        La catégorie est le filet indispensable : les articles achetés — un
        couvre-joint TECHNAL, un vitrage TIV — portent leur catégorie sans
        avoir nécessairement de triplet famille renseigné.
        """
        self.ensure_one()
        valeur = (
            self.subfamily_id.fma_famille_appro
            or self.family_id.fma_famille_appro
        )
        if valeur:
            return valeur
        categorie = self.categ_id
        while categorie:
            if categorie.fma_famille_appro:
                return categorie.fma_famille_appro
            categorie = categorie.parent_id
        return False
