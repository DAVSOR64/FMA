
from odoo import models

ORDER = [
    "Débit FMA",
    "CU (banc) FMA",
    "Usinage FMA",
    "Montage FMA",
    "Vitrage FMA",
    "Emballage FMA",
]

def _norm(v):
    return (v or "").lower()

class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def action_resequence_fma(self):
        for production in self:
            for wo in production.workorder_ids:
                for idx, label in enumerate(ORDER):
                    if _norm(label) in _norm(wo.name):
                        if wo.operation_id:
                            wo.operation_id.sequence = (idx + 1) * 10
            production.workorder_ids._compute_op_sequence()
        return True
