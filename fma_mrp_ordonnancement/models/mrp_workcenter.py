# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

from .constants import FMA_POSTE_TYPES, FMA_POSTE_TOKENS

_logger = logging.getLogger(__name__)


class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'

    fma_poste_type = fields.Selection(
        FMA_POSTE_TYPES,
        string="Type de poste (FMA)",
        index=True,
        help="Rôle métier du poste dans la gamme FMA. Sert à ventiler les "
             "heures prévues des ordres de travail sur l'OF et à appliquer le "
             "barème de score correspondant. Renseigner ce champ évite de "
             "dépendre du libellé exact du poste de charge.",
    )

    @api.model
    def _fma_deviner_poste_type(self, libelle):
        """Déduit un type de poste depuis un libellé. Usage installation."""
        texte = (libelle or '').strip().lower()
        for jeton, poste_type in FMA_POSTE_TOKENS:
            if jeton in texte:
                return poste_type
        return False

    def write(self, vals):
        result = super().write(vals)
        if 'fma_poste_type' in vals:
            # Le type de poste conditionne la ventilation des heures : on
            # redemande le calcul sur les OF ouverts.
            self.env['mrp.production']._fma_marquer_recalcul(
                self.env['mrp.production']._fma_champs_heures_et_scores()
            )
        return result
