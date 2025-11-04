import pytz
from datetime import datetime, time
from odoo import api, models, fields


class MrpWorkOrder(models.Model):
    _inherit = "mrp.workorder"

    date_macro = fields.Datetime("Macro Date")


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    def action_confirm(self):
        self._compute_date_macro()
        return super().action_confirm()

    def write(self, vals):
        res = super().write(vals)
        self._compute_date_macro()
        return res

    def _compute_date_macro(self):
        for production in self:
            date_delivery = (
                production.procurement_group_id.mrp_production_ids.move_dest_ids.group_id.sale_id.commitment_date
                or production.date_finished
            )

            manufacturing_lead = production.company_id.manufacturing_lead
            calendar = (
                production.company_id.resource_calendar_id
                or self.env.ref('resource.resource_calendar_std')
            )

            # Calcul de la deadline en jours ouvrés
            deadline_production = calendar.plan_days(-manufacturing_lead, date_delivery)
            last_date = calendar.plan_days(-1, deadline_production)

            for work in production.workorder_ids.sorted("id", reverse=True):
                workcenter_calendar = work.workcenter_id.resource_calendar_id or calendar
                work.date_macro = last_date

                last_date2 = workcenter_calendar._attendance_intervals_batch(
                    datetime.combine(last_date, time.min).replace(tzinfo=pytz.UTC),
                    datetime.combine(last_date, time.max).replace(tzinfo=pytz.UTC),
                    resources=work.workcenter_id.resource_id
                )

                if last_date2 and work.workcenter_id.resource_id.id in last_date2:
                    first_interval = last_date2[work.workcenter_id.resource_id.id]._items
                    if first_interval:
                        last_date2 = first_interval[0][0]
                        last_date = last_date.replace(
                            hour=last_date2.hour, minute=0, second=0, microsecond=0
                        )

                last_date = workcenter_calendar.plan_hours(-work.duration_expected / 60, last_date)
                last_date = workcenter_calendar.plan_days(-1, last_date)

            # 🔹 Mise à jour des dates de production
            if production.workorder_ids:
                all_dates = [w.date_macro for w in production.workorder_ids if w.date_macro]
                if all_dates:
                    production.sudo().with_context(no_recompute=True).update({
                        'date_start': min(all_dates),
                        'date_finished': max(all_dates),
                    })
