import logging
from odoo import models, fields, api
from datetime import timedelta

_logger = logging.getLogger(__name__)

class MrpProduction(models.Model):
    _inherit = 'mrp.production'
    ir_log_ids = fields.One2many('ir.logging', 'connector_id')


    def button_plan(self):
        _logger.warning("**********dans le module********* %s ")
        res = super().button_plan()

        for production in self:
            previous_op = None
            for workorder in sorted(production.workorder_ids, key=lambda wo: wo.operation_id.sequence):
                if not previous_op:
                    workorder.date_start = production.date_start
                else:
                    delay_obj = self.env['x_delai_entre_operatio'].search([
                        ('x_studio_poste_de_travail_deb', '=', previous_op.workcenter_id.id),
                        ('x_studio_poste_de_travail_fin', '=', workorder.workcenter_id.id)
                    ], limit=1)
                    
                    delay_minutes = delay_obj.x_studio_dlai_entre_opration if delay_obj else 0
                    _logger.warning("**********Delai********* %s " % str(delay_minutes))
                    start_date = previous_op.date_finished + timedelta(minutes=delay_minutes)
                    workorder.date_start = start_date
        
                duration = workorder.duration_expected or 0.0
                workorder.date_finished = workorder.date_start + timedelta(minutes=duration)
        
                previous_op = workorder

        return res
