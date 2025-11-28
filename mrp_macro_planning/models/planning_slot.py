import pytz

from datetime import datetime, time

from odoo import api, models, fields


class PlanningSlot(models.Model):
    _inherit = "planning.slot"

    workcenter_id = fields.Many2one("mrp.workcenter", "Workcenter")