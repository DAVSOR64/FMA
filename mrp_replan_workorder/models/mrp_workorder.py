# -*- coding: utf-8 -*-
import logging
from datetime import timedelta
from odoo import models, fields

_logger = logging.getLogger(__name__)


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    def write(self, values):
        # éviter récursion quand on met à jour nous-mêmes
        if self.env.context.get("skip_shift_chain"):
            return super().write(values)

        # On ne déclenche que si on bouge date_start via planning
        trigger = "date_start" in values
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
        """Décale toutes les WO suivantes du même delta, et aligne macro_planned_start sur date_start."""
        self.ensure_one()
        mo = self.production_id
        if not mo:
            return

        # Tri identique à celui de tes scripts (séquence opération puis id)
        all_wos = mo.workorder_ids.filtered(lambda w: w.state not in ("done", "cancel"))
        all_wos = sorted(all_wos, key=lambda w: (w.operation_id.sequence if w.operation_id else 0, w.id))

        # index WO déplacé
        try:
            idx = next(i for i, w in enumerate(all_wos) if w.id == self.id)
        except StopIteration:
            return

        # on ne décale QUE les suivantes (idx+1 -> fin)
        following = all_wos[idx + 1:]

        # Optionnel : mettre macro_planned_start = date_start sur la WO déplacée aussi
        if "macro_planned_start" in self._fields:
            self.with_context(skip_shift_chain=True, mail_notrack=True).write({
                "macro_planned_start": self.date_start,
            })

        for wo in following:
            if not wo.date_start:
                continue

            start_dt = fields.Datetime.to_datetime(wo.date_start) + delta

            # fin = start + durée (minutes)
            duration_min = wo.duration_expected or 0.0
            end_dt = start_dt + timedelta(minutes=duration_min)

            vals = {
                "date_start": start_dt,
                "date_finished": end_dt,
            }

            if "macro_planned_start" in wo._fields:
                vals["macro_planned_start"] = start_dt

            wo.with_context(skip_shift_chain=True, mail_notrack=True).write(vals)

            _logger.info(
                "SHIFT | MO %s | WO %s | delta=%s | new_start=%s | new_end=%s",
                mo.name, wo.name, delta, start_dt, end_dt
            )

        # (optionnel mais utile) recaler les dates de l'OF sur les WO
        if hasattr(mo, "_update_mo_dates_from_workorders_dates_only"):
            mo.with_context(skip_shift_chain=True, mail_notrack=True)._update_mo_dates_from_workorders_dates_only()
