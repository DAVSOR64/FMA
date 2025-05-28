from odoo import models


class MrpWorkorder(models.Model):
    _inherit = "mrp.workorder"

    def write(self, values):
        res = super().write(values)
        trigger_fields = {'date_start', 'date_finished'}
        if trigger_fields.intersection(values.keys()):
            self._replan_workorder()
        return res

    def _replan_workorder(self):
        for wo in self:
            conflicted_dict = wo._get_conflicted_workorder_ids()
            if conflicted_dict.get(wo.id):
                for conflicted in self.browse(conflicted_dict.get(wo.id)):
                    conflicted._plan_workorder(replan=True)
            for needed in wo.needed_by_workorder_ids:
                needed._plan_workorder(replan=True)
                needed._replan_workorder()

