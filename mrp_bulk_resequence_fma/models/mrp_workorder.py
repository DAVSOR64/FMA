
from odoo import models, fields

class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    op_sequence = fields.Integer(
        string="Séquence opération",
        related="operation_id.sequence",
        store=True,
        readonly=True,
    )
