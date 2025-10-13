import pytz

from datetime import datetime, time

from odoo import api, models, fields


class MrpWorkOrder(models.Model):
    _inherit = "mrp.workorder"

    date_macro = fields.Date("Macro Date")


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
            date_delivery = production.procurement_group_id.mrp_production_ids.move_dest_ids.group_id.sale_id.commitment_date or production.date_finished
            manufacturing_lead = production.company_id.manufacturing_lead
            calendar = production.company_id.resource_calendar_id or self.env.ref('resource.resource_calendar_std')
            # date_delivery = date_delivery.replace(hour=8, minute=0, second=0, microsecond=0)

            # Calcul de la deadline en jours ouvrés
            deadline_production = calendar.plan_days(-manufacturing_lead, date_delivery)

            # On recule d’1 jour ouvré
            last_date = calendar.plan_days(-1, deadline_production)

            for work in production.workorder_ids.sorted("date_start", reverse=True):
                workcenter_calendar = work.workcenter_id.resource_calendar_id or calendar
                work.date_macro = last_date

                # Chercher la début de la journée ouvrée correspondant à last_date
                last_date2 = workcenter_calendar._attendance_intervals_batch(
                    datetime.combine(last_date, time.min).replace(tzinfo=pytz.UTC),
                    datetime.combine(last_date, time.max).replace(tzinfo=pytz.UTC),
                    resources=work.workcenter_id.resource_id)
                last_date2 = last_date2[work.workcenter_id.resource_id.id]._items[0][0]
                last_date = last_date.replace(hour=last_date2.hour, minute=0, second=0, microsecond=0)

                # Reculer selon la durée prévue
                last_date = workcenter_calendar.plan_hours(-work.duration_expected / 60, last_date)

                last_date = workcenter_calendar.plan_days(-1, last_date)

    # @api.depends('workorder_ids.date_macro')
    # def _compute_dates_from_workorders(self):
    #     for production in self:
    #         dates = [wo.date_macro for wo in production.workorder_ids if wo.date_macro]
    #         if dates:
    #             production.date_start = min(dates)
    #             production.date_finished = max(dates)
    #         else:
    #             production.date_start = False
    #             production.date_finished = False
    #
    # date_start = fields.Datetime(
    #     string="Date Start",
    #     compute="_compute_dates_from_workorders",
    #     store=True,
    #     readonly=False,
    # )
    # date_finished = fields.Datetime(
    #     string="Date Finished",
    #     compute="_compute_dates_from_workorders",
    #     store=True,
    #     readonly=False,
    # )
