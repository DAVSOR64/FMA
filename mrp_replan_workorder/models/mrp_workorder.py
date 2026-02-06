# -*- coding: utf-8 -*-
from odoo import models, fields

class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    macro_planned_start = fields.Datetime(
        string="Macro (début planifié)",
        help="Début planifié calculé depuis la date de livraison (planning macro).",
        copy=False,
        index=True,
        tracking=False,
    )
    date_macro = fields.Datetime(
        string="Date Macro",
        help="Début planifié",
        copy=False,
        index=True,
        tracking=False,
    )
