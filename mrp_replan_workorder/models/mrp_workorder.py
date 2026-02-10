# -*- coding: utf-8 -*-
import logging
from datetime import timedelta
from odoo import models, fields

_logger = logging.getLogger(__name__)


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    def write(self, values):
        # éviter boucle
        if self.env.context.get("skip_macro_replan"):
            return super().write(values)

        res = super().write(values)

        trigger_fields = {"date_start", "date_finished"}
        if trigger_fields.intersection(values.keys()):
            for wo in self:
                wo._macro_replan_from_here()

        return res

    def _macro_replan_from_here(self):
        """Replan selon règle métier : lendemain ouvré matin + respect macro_planned_start."""
        self.ensure_one()

        mo = self.production_id
        if not mo:
            return

        # WO de l'OF triées
        wos = mo.workorder_ids.filtered(lambda w: w.state not in ("done", "cancel"))
        wos = sorted(wos, key=lambda w: (w.operation_id.sequence if w.operation_id else 0, w.id))
        if not wos:
            return

        # index du WO déplacé
        try:
            idx = next(i for i, w in enumerate(wos) if w.id == self.id)
        except StopIteration:
            return

        # fin précédente = WO juste avant (si existe)
        prev_end_dt = None
        if idx > 0 and wos[idx - 1].date_finished:
            prev_end_dt = fields.Datetime.to_datetime(wos[idx - 1].date_finished)

        # On repart du WO déplacé et on enchaîne jusqu'à la fin
        for i in range(idx, len(wos)):
            wo = wos[i]

            # base : si c'est le premier de la chaîne, on prend la date posée par l'utilisateur
            # sinon on calcule depuis prev_end_dt
            user_start = fields.Datetime.to_datetime(wo.date_start) if wo.date_start else None
            macro_start = fields.Datetime.to_datetime(wo.macro_planned_start) if getattr(wo, "macro_planned_start", False) else None

            if prev_end_dt:
                prev_day = prev_end_dt.date()
                next_day = mo._next_working_day(prev_day, wo.workcenter_id)
                chain_start = mo._morning_dt(next_day, wo.workcenter_id)
            else:
                chain_start = None

            # start = max(macro, chain_start, user_start)
            candidates = [d for d in (user_start, macro_start, chain_start) if d]
            if not candidates:
                continue
            start_dt = max(candidates)

            duration_min = wo.duration_expected or 0.0
            end_dt = start_dt + timedelta(minutes=duration_min)

            wo.with_context(skip_macro_replan=True, mail_notrack=True).write({
                "date_start": start_dt,
                "date_finished": end_dt,
            })

            _logger.info(
                "MACRO REPLAN | MO %s | WO %s | macro=%s | chain=%s | start=%s | end=%s",
                mo.name, wo.name, macro_start, chain_start, start_dt, end_dt
            )

            prev_end_dt = end_dt
