# -*- coding: utf-8 -*-
from odoo import api, fields, models


class FmaComplexiteNiveau(models.Model):
    _name = 'fma.complexite.niveau'
    _description = "Niveau de complexité menuiserie"
    _order = 'sequence, code'

    code = fields.Char(
        string="Code",
        required=True,
        help="Code utilisé dans le champ « Niveau de complexité » de l'OF, "
             "par exemple le A de « A*3 ».",
    )
    name = fields.Char(string="Libellé", required=True, translate=True)
    poids = fields.Integer(
        string="Poids",
        default=1,
        help="Poids du niveau dans le score de complexité de l'OF. "
             "Le classeur Excel utilisait A=1, B=2, C=3 et ne pondérait pas M.",
    )
    sequence = fields.Integer(string="Séquence", default=10)
    active = fields.Boolean(string="Actif", default=True)

    _code_unique = models.Constraint(
        'UNIQUE(code)',
        "Le code d'un niveau de complexité doit être unique.",
    )

    @api.model
    def _poids_par_code(self):
        """Retourne {code majuscule: poids} pour les niveaux actifs."""
        return {
            (niveau.code or '').strip().upper(): niveau.poids
            for niveau in self.search([])
            if niveau.code
        }

    def _fma_invalider_scores(self):
        Production = self.env['mrp.production']
        Production._fma_marquer_recalcul(
            ['fma_nb_reperes', 'fma_score_complexite'] + Production._fma_champs_scores()
        )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._fma_invalider_scores()
        return records

    def write(self, vals):
        result = super().write(vals)
        if {'code', 'poids', 'active'} & set(vals):
            self._fma_invalider_scores()
        return result

    def unlink(self):
        niveaux = self.exists()
        result = super().unlink()
        niveaux._fma_invalider_scores()
        return result
