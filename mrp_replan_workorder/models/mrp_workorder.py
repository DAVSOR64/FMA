# -*- coding: utf-8 -*-
import logging
from datetime import timedelta
from odoo import models, fields

_logger = logging.getLogger(__name__)


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    macro_planned_start = fields.Datetime(
        string="Date debut calculée",
        copy=False,
        help="Date deb calculée."
    )
    def write(self, values):
        # évite la récursion quand on décale nous-mêmes les autres WO
        if self.env.context.get("skip_shift_chain"):
            return super().write(values)

        trigger = "date_start" in values  # ✅ ton champ de planning
        old_starts = {}

        if trigger:
            for wo in self:
                old_starts[wo.id] = fields.Datetime.to_datetime(wo.date_start) if wo.date_start else None

        res = super().write(values)

        if trigger:
            for wo in self:
                old_start = old_starts.get(wo.id)
                new_start = fields.Datetime.to_datetime(wo.date_start) if wo.date_start else None
                if not old_start or not new_start:
                    continue

                delta = new_start - old_start
                if not delta:
                    continue

                wo._shift_following_workorders(delta)

        return res

    def _shift_following_workorders(self, delta):
        """Décale toutes les WO suivantes du même delta (date_start + date_finished)."""
        self.ensure_one()
        mo = self.production_id
        if not mo:
            return

        # WO actives
        all_wos = mo.workorder_ids.filtered(lambda w: w.state not in ("done", "cancel"))

        # tri stable (comme tes macros) : séquence opération puis id
        all_wos = sorted(all_wos, key=lambda w: (w.operation_id.sequence if w.operation_id else 0, w.id))

        try:
            idx = next(i for i, w in enumerate(all_wos) if w.id == self.id)
        except StopIteration:
            return

        following = all_wos[idx + 1:]

        for wo in following:
            # Si une WO n'a pas encore été planifiée, on ne la touche pas
            # (si tu veux aussi planifier celles-ci, dis-le et je te mets la variante)
            if not wo.date_start:
                continue

            start_dt = fields.Datetime.to_datetime(wo.date_start) + delta

            # fin = start + durée prévue
            duration_min = wo.duration_expected or 0.0
            end_dt = start_dt + timedelta(minutes=duration_min)

            # ✅ IMPORTANT : write AVEC contexte pour ne pas relancer le chain shift
            wo.with_context(skip_shift_chain=True, mail_notrack=True).write({
                "date_start": start_dt,
                "date_finished": end_dt,
            })

            _logger.info(
                "SHIFT | MO %s | WO %s | delta=%s | new_start=%s | new_end=%s",
                mo.name, wo.name, delta, start_dt, end_dt
            )
