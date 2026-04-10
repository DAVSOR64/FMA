from odoo import models, fields, api
from collections import defaultdict
from datetime import timedelta


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    def _get_duration_hours(self):
        """Durée en heures fiable"""
        self.ensure_one()
        if self.duration_expected:
            return self.duration_expected / 60.0
        if self.duration:
            return self.duration / 60.0
        return 0.0