from odoo import models, fields
from datetime import timedelta
import math
import logging

_logger = logging.getLogger(__name__)

MINUTES_PER_DAY = 8 * 60  # 8h/jour


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    # ⚠️ IMPORTANT : doit être un vrai champ Odoo (sinon mrp_workorder.write ne peut pas le lire)
    macro_plan_freeze = fields.Boolean(default=False)

    def button_plan(self):
        _logger.warning("********** PLAN (macro inspired) **********")

        # 1) Backup macros
        macro_backup = {}
        for mo in self:
            for wo in mo.workorder_ids:
                if wo.macro_planned_start:
                    macro_backup[wo.id] = wo.macro_planned_start
        _logger.info("BUTTON_PLAN : sauvegarde %s macro_planned_start", len(macro_backup))

        # 2) Freeze DB pour empêcher les resets date_start/date_finished pendant planif
        self.write({"macro_plan_freeze": True})

        # 3) Super
        res = super().button_plan()

        # 4) Restaurer macro + appliquer dates (macro -> planned + réel)
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
                end_dt = mo._macro_end_datetime_from_start(start_dt, required_days)

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

            # Recaler OF (début = première macro, fin = macro_forced_end si rempli)
            first = mo.workorder_ids.filtered("macro_planned_start").sorted("macro_planned_start")[:1]
            if first:
                mo.date_start = first.macro_planned_start

            if getattr(mo, "macro_forced_end", False):
                mo.date_finished = mo.macro_forced_end
                mo.date_deadline = mo.macro_forced_end

        # 5) Unfreeze
        self.write({"macro_plan_freeze": False})

        return res

    # -------------------------
    # Boutons attendus par la vue XML
    # -------------------------
    def action_debug_macro_dates(self):
        """Étape 1 : debug macros uniquement (ne touche pas aux dates planned)."""
        for mo in self:
            wos = mo.workorder_ids.filtered("macro_planned_start").sorted("macro_planned_start")
            _logger.info("=== DEBUG MACRO %s | WO=%s ===", mo.name, len(wos))
            for wo in wos:
                dur = float(wo.duration_expected or 0.0)
                req_days = int(math.ceil(dur / MINUTES_PER_DAY)) if dur else 1
                _logger.info(
                    "WO %-30s | wc=%s | macro_start=%s | dur=%s min | req_days=%s",
                    wo.name, wo.workcenter_id.name if wo.workcenter_id else "-", wo.macro_planned_start, dur, req_days
                )
        return True

    def action_apply_macro_to_planned_dates(self):
        """Étape 2 : appliquer macro -> dates (planned + réel), sans passer par button_plan."""
        for mo in self:
            wos = mo.workorder_ids.filtered("macro_planned_start").sorted("macro_planned_start")
            for wo in wos:
                start_dt = wo.macro_planned_start
                dur = float(wo.duration_expected or 0.0)
                req_days = int(math.ceil(dur / MINUTES_PER_DAY)) if dur else 1
                end_dt = mo._macro_end_datetime_from_start(start_dt, req_days)

                wo.write({
                    "date_start": start_dt,
                    "date_finished": end_dt,
                    "date_planned_start": start_dt,
                    "date_planned_finished": end_dt,
                })
        return True

    # -------------------------
    # Helpers
    # -------------------------
    def _macro_end_datetime_from_start(self, start_dt, req_days):
        """Fin = fin de journée du dernier jour ouvré."""
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
        # Utilise ton helper WO si dispo, sinon adapte ici
        return self.env["mrp.workorder"]._combine_day_time(day, hour=17, minute=30)