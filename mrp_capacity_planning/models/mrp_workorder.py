from odoo import models

class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    def _get_duration_hours(self):
        self.ensure_one()
        if self.duration_expected:
            return self.duration_expected / 60.0
        if self.duration:
            return self.duration / 60.0
        return 0.0
