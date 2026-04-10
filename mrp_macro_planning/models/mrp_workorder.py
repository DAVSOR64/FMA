# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    macro_planned_start = fields.Datetime(
        string="Macro (début planifié)",
        copy=False,
        index=True,
    )

    macro_end = fields.Datetime(
        string="Fin macro",
        compute="_compute_macro_end",
        store=True,
    )

    @api.depends("macro_planned_start", "duration_expected", "date_finished")
    def _compute_macro_end(self):
        for wo in self:
            if not wo.macro_planned_start:
                wo.macro_end = False
                continue

            if wo.date_finished:
                wo.macro_end = wo.date_finished
                continue

            duration_minutes = float(wo.duration_expected or 0.0)
            if duration_minutes <= 0:
                duration_minutes = 1.0

            wo.macro_end = wo.macro_planned_start + timedelta(minutes=duration_minutes)
