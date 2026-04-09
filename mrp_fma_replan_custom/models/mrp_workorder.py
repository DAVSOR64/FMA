# -*- coding: utf-8 -*-

from odoo import fields, models


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    op_sequence = fields.Integer(
        string="Séquence opération",
        related="operation_id.sequence",
        store=True,
        readonly=True,
    )