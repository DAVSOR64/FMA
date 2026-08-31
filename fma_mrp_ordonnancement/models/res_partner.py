# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .constants import FMA_CATEGORIES_APPRO


class ResPartner(models.Model):
    _inherit = 'res.partner'

    fma_categorie_appro = fields.Selection(
        FMA_CATEGORIES_APPRO,
        string="Famille d'approvisionnement (FMA)",
        index=True,
        help="Famille de composants fournie par ce fournisseur. Remplace les "
             "listes de noms codées en dur dans les formules du classeur "
             "Excel : ajouter un fournisseur se fait désormais ici, sans "
             "modifier de formule.",
    )

    def write(self, vals):
        result = super().write(vals)
        if 'fma_categorie_appro' in vals:
            self.env['mrp.production']._fma_marquer_recalcul(
                self.env['mrp.production']._fma_champs_appro()
            )
        return result
