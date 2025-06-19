from odoo import models, fields, api
from datetime import timedelta

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    def button_plan(self):
        res = super().button_plan()

        for production in self:
            previous_op = None
            for workorder in production.workorder_ids.sorted('sequence'):
                if not previous_op:
                    workorder.date_planned_start = production.date_planned_start
                else:
                    delay_obj = self.env['x_delai_entre_operatio'].search([
                        ('x_studio_poste_de_travail_deb', '=', previous_op.workcenter_id.id),
                        ('x_studio_poste_de_travail_fin', '=', workorder.workcenter_id.id)
                    ], limit=1)

                    delay_minutes = delay_obj.x_studio_dlai_entre_opration if delay_obj else 0
                    start_date = previous_op.date_planned_finished + timedelta(minutes=delay_minutes)
                    workorder.date_planned_start = start_date

                duration = workorder.duration_expected or 0.0
                workorder.date_planned_finished = workorder.date_planned_start + timedelta(minutes=duration)

                previous_op = workorder

        return res
