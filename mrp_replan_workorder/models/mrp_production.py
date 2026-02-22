
from odoo import models, fields
import logging
from datetime import timedelta

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    # Empêche les boucles lors du bouton Programmer
    def button_plan(self):
        _logger.info("BUTTON PLAN with skip_macro_recalc context")
        return super(MrpProduction, self.with_context(skip_macro_recalc=True)).button_plan()

    def write(self, vals):
        if self.env.context.get("skip_macro_recalc"):
            return super().write(vals)

        start_changed = "date_start" in vals
        end_changed = "x_studio_date_fin" in vals

        res = super().write(vals)

        for mo in self:
            try:
                if start_changed and mo.date_start:
                    _logger.info("Recalc macro FORWARD depuis date_start pour %s", mo.name)
                    mo._macro_recalc_from_date_start()

                elif end_changed and mo.x_studio_date_fin:
                    _logger.info("Recalc macro BACKWARD depuis x_studio_date_fin pour %s", mo.name)
                    mo._macro_recalc_from_x_end_date()

            except Exception as e:
                _logger.exception("Erreur recalcul macro pour %s : %s", mo.name, e)

        return res

    # Forward depuis date_start
    def _macro_recalc_from_date_start(self):
        self.ensure_one()
        if not self.date_start:
            return

        if hasattr(self, "_recalculate_macro_forward"):
            self.with_context(skip_macro_recalc=True)._recalculate_macro_forward()
        else:
            _logger.warning("Méthode _recalculate_macro_forward absente sur %s", self.name)

        last_wo = self.workorder_ids.filtered(lambda w: w.macro_planned_start)
        last_wo = last_wo.sorted(key=lambda w: w.macro_planned_start)[-1:]

        if last_wo:
            wo = last_wo[0]
            duration = wo.duration_expected or 0.0
            end_dt = wo.macro_planned_start + timedelta(minutes=duration)
        else:
            end_dt = self.date_start

        end_day = fields.Datetime.to_datetime(end_dt).date()

        vals = {
            "x_studio_date_fin": end_day,
            "date_finished": end_dt,
            "date_deadline": end_dt,
        }

        self.with_context(skip_macro_recalc=True, mail_notrack=True).write(vals)

    # Backward depuis x_studio_date_fin
    def _macro_recalc_from_x_end_date(self):
        self.ensure_one()
        if not self.x_studio_date_fin:
            return

        end_dt = fields.Datetime.to_datetime(self.x_studio_date_fin) + timedelta(hours=18)

        if hasattr(self, "_recalculate_macro_backward"):
            self.with_context(skip_macro_recalc=True)._recalculate_macro_backward()
        else:
            _logger.warning("Méthode _recalculate_macro_backward absente sur %s", self.name)

        first_wo = self.workorder_ids.filtered(lambda w: w.macro_planned_start)
        first_wo = first_wo.sorted(key=lambda w: w.macro_planned_start)[:1]

        start_dt = first_wo[0].macro_planned_start if first_wo else self.date_start

        vals = {
            "date_start": start_dt,
            "date_finished": end_dt,
            "date_deadline": end_dt,
        }

        self.with_context(skip_macro_recalc=True, mail_notrack=True).write(vals)
