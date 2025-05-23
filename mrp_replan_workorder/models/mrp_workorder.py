from odoo import models


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    def write(self, values):
        res = super().write(values)
        if values.get("date_start", False) or values.get("date_finished", False):
            self._replan_workorder()
        return res

    def _replan_workorder(self):
        for wo in self:
            conflicted_dict = wo._get_conflicted_workorder_ids()
            if conflicted_dict.get(wo.id):
                conflicted = self.browse(conflicted_dict.get(wo.id))
                conflicted._plan_workorder(replan=True)
            for needed in wo.needed_by_workorder_ids:
                needed._plan_workorder(replan=True)
                needed._replan_workorder()

