# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)

SEUIL_AUTO_REFRESH = 100


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    macro_end = fields.Datetime(
        string="Fin macro",
        compute="_compute_macro_end",
        store=True,
    )

    @api.depends("macro_planned_start", "duration_expected", "date_finished")
    def _compute_macro_end(self):
        """
        Fin utilisée par le macro planning.
        Priorité :
        1) date_finished si elle existe déjà et qu'on a un début macro
        2) sinon calcul depuis macro_planned_start + duration_expected (en minutes)
        """
        for wo in self:
            macro_end = False

            if wo.macro_planned_start:
                if wo.date_finished:
                    macro_end = wo.date_finished
                elif wo.duration_expected:
                    # duration_expected est géré ici en minutes
                    macro_end = wo.macro_planned_start + timedelta(minutes=float(wo.duration_expected))
                else:
                    # fallback minimum pour que le gantt voie quand même la barre
                    macro_end = wo.macro_planned_start + timedelta(minutes=1)

            wo.macro_end = macro_end

    def write(self, vals):
        """
        Auto-refresh du cache charge si modification des champs critiques
        ET si nombre de workorders actifs <= SEUIL_AUTO_REFRESH
        """
        res = super().write(vals)

        critical_fields = {
            "date_start",
            "date_finished",
            "date_planned_finished",
            "duration_expected",
            "duration",
            "state",
            "workcenter_id",
            "macro_planned_start",
        }

        if any(f in vals for f in critical_fields):
            nb_active = self.env["mrp.workorder"].search_count([
                ("state", "not in", ("done", "cancel")),
                ("macro_planned_start", "!=", False),
            ])

            if nb_active <= SEUIL_AUTO_REFRESH:
                _logger.info("AUTO-REFRESH charge : %d workorders actifs", nb_active)
                try:
                    self.env["mrp.workorder.charge.cache"].refresh()
                except Exception as e:
                    _logger.error("Erreur auto-refresh charge : %s", e)
            else:
                _logger.info(
                    "AUTO-REFRESH désactivé : %d workorders (seuil=%d)",
                    nb_active,
                    SEUIL_AUTO_REFRESH,
                )

        return res

    @api.model_create_multi
    def create(self, vals_list):
        """
        Auto-refresh après création si sous le seuil
        """
        res = super().create(vals_list)

        nb_active = self.env["mrp.workorder"].search_count([
            ("state", "not in", ("done", "cancel")),
            ("macro_planned_start", "!=", False),
        ])

        if nb_active <= SEUIL_AUTO_REFRESH:
            _logger.info("AUTO-REFRESH charge après création : %d workorders", nb_active)
            try:
                self.env["mrp.workorder.charge.cache"].refresh()
            except Exception as e:
                _logger.error("Erreur auto-refresh charge : %s", e)

        return res