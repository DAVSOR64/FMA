from odoo import models
from datetime import timedelta
import math
import logging

_logger = logging.getLogger(__name__)

MINUTES_PER_DAY = 8 * 60  # 8h de prod / jour (à ajuster si besoin)


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    macro_plan_freeze = False  # verrou DB pour empêcher l'effacement des dates

    def button_plan(self):
        _logger.warning("********** PLAN (macro inspired) **********")

        # 1) Backup des macros
        macro_backup = {}
        for mo in self:
            for wo in mo.workorder_ids:
                if wo.macro_planned_start:
                    macro_backup[wo.id] = wo.macro_planned_start
        _logger.info("BUTTON_PLAN : sauvegarde %s macro_planned_start", len(macro_backup))

        # 2) Verrou pour éviter que Odoo efface date_start/date_finished
        for mo in self:
            mo.macro_plan_freeze = True

        # 3) Planification standard Odoo
        res = super().button_plan()

        # 4) Ré-application des dates macro
        for mo in self:
            workorders = mo.workorder_ids.sorted(
                key=lambda w: w.macro_planned_start or w.date_start or w.id
            )

            for wo in workorders:
                saved_macro = macro_backup.get(wo.id)
                if not saved_macro:
                    continue

                wo.macro_planned_start = saved_macro
                start_dt = saved_macro

                duration = float(wo.duration_expected or 0.0)
                required_days = int(math.ceil(duration / MINUTES_PER_DAY)) if duration else 1

                end_dt = self._macro_end_datetime_from_start(start_dt, required_days)

                wo.write({
                    "date_start": start_dt,
                    "date_finished": end_dt,
                    "date_planned_start": start_dt,
                    "date_planned_finished": end_dt,
                })

                _logger.info(
                    "WO %s | start=%s end=%s | dur=%s min => %s j",
                    wo.name, start_dt, end_dt, duration, required_days
                )

        # 5) Recaler l'OF
        for mo in self:
            first_wo = mo.workorder_ids.sorted(key=lambda w: w.macro_planned_start)[0]
            if first_wo and first_wo.macro_planned_start:
                mo.date_start = first_wo.macro_planned_start

            if mo.macro_forced_end:
                mo.date_finished = mo.macro_forced_end
                mo.date_deadline = mo.macro_forced_end

        # 6) Déverrouillage
        for mo in self:
            mo.macro_plan_freeze = False

        return res

    def _macro_end_datetime_from_start(self, start_dt, req_days):
        """Fin = fin de journée du dernier jour ouvré"""
        start_day = start_dt.date()
        last_day = self._add_working_days(start_day, req_days - 1)
        return self._evening_dt(last_day)

    def _add_working_days(self, day, n):
        cur = day
        remaining = abs(n)
        step = 1 if n >= 0 else -1
        while remaining:
            cur = cur + timedelta(days=step)
            if cur.weekday() < 5:  # lun-ven
                remaining -= 1
        return cur

    def _evening_dt(self, day):
        return self.env["mrp.workorder"]._combine_day_time(day, hour=17, minute=30)