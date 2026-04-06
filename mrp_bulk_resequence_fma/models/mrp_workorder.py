
from odoo import models, fields, api

class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    op_sequence = fields.Integer(compute="_compute_op_sequence", store=True)

    @api.depends('operation_id.sequence')
    def _compute_op_sequence(self):
        for wo in self:
            wo.op_sequence = wo.operation_id.sequence or 0
