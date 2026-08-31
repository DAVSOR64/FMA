# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .constants import FMA_POSTE_TYPES, FMA_POSTES_SCORES


class FmaBaremeScore(models.Model):
    """Barèmes « heures par repère -> score », onglet SEQUENCAGE.

    Une ligne = une tranche. La borne basse est incluse, la borne haute est
    exclue. Une borne haute vide signifie « pas de limite ».
    """

    _name = 'fma.bareme.score'
    _description = "Barème de score par poste de charge"
    _order = 'poste_type, borne_min'
    _rec_name = 'display_name'

    poste_type = fields.Selection(
        FMA_POSTE_TYPES,
        string="Type de poste",
        required=True,
        index=True,
    )
    borne_min = fields.Float(
        string="Heures/repère à partir de",
        default=0.0,
        digits=(10, 3),
        help="Borne incluse.",
    )
    borne_max = fields.Float(
        string="Heures/repère jusqu'à",
        digits=(10, 3),
        help="Borne exclue. Laisser vide pour la dernière tranche.",
    )
    score = fields.Integer(string="Score", required=True)
    active = fields.Boolean(string="Actif", default=True)
    display_name = fields.Char(compute='_compute_display_name', store=True)

    @api.depends('poste_type', 'borne_min', 'borne_max', 'score')
    def _compute_display_name(self):
        labels = dict(FMA_POSTE_TYPES)
        for bareme in self:
            if bareme.borne_max:
                tranche = "%.2f à %.2f" % (bareme.borne_min, bareme.borne_max)
            else:
                tranche = "%.2f et plus" % bareme.borne_min
            bareme.display_name = "%s : %s -> %s" % (
                labels.get(bareme.poste_type, '-'), tranche, bareme.score,
            )

    @api.constrains('borne_min', 'borne_max')
    def _check_bornes(self):
        for bareme in self:
            if bareme.borne_max and bareme.borne_max <= bareme.borne_min:
                raise ValidationError(
                    "La borne haute doit être strictement supérieure à la borne basse "
                    "(poste %s)." % (bareme.poste_type or '-')
                )

    @api.model
    def _postes_scores(self):
        """Postes réellement notés : ceux qui portent au moins un barème."""
        postes = []
        for poste in self.search([]).mapped('poste_type'):
            if poste and poste not in postes:
                postes.append(poste)
        return postes or list(FMA_POSTES_SCORES)

    @api.model
    def _bareme_par_poste(self):
        """Retourne {poste_type: [(borne_min, borne_max, score), ...]} trié."""
        resultat = {}
        for bareme in self.search([], order='poste_type, borne_min'):
            resultat.setdefault(bareme.poste_type, []).append(
                (bareme.borne_min, bareme.borne_max, bareme.score)
            )
        return resultat

    @api.model
    def _score_pour(self, tranches, ratio):
        """Applique un barème déjà chargé à un ratio heures/repère."""
        for borne_min, borne_max, score in tranches:
            if ratio < borne_min:
                continue
            if not borne_max or ratio < borne_max:
                return score
        return 0

    # ------------------------------------------------------------------
    # Invalidation
    #
    # Aucune relation ne lie un barème à un OF : Odoo ne peut donc pas
    # déduire seul qu'un changement de barème doit recalculer les scores.
    # On le déclenche explicitement.
    # ------------------------------------------------------------------
    def _fma_invalider_scores(self):
        Production = self.env['mrp.production']
        Production._fma_marquer_recalcul(Production._fma_champs_scores())

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._fma_invalider_scores()
        return records

    def write(self, vals):
        result = super().write(vals)
        self._fma_invalider_scores()
        return result

    def unlink(self):
        baremes = self.exists()
        result = super().unlink()
        baremes._fma_invalider_scores()
        return result
