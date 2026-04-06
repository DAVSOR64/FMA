
import logging

from odoo import models

_logger = logging.getLogger(__name__)

ORDER = [
    "Débit FMA",
    "CU (banc) FMA",
    "Usinage FMA",
    "Montage FMA",
    "Vitrage FMA",
    "Emballage FMA",
]


def _norm(value):
    return (value or "").strip().lower()


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def _fma_rank(self, wo):
        values = [
            _norm(wo.name),
            _norm(wo.workcenter_id.name),
            _norm(wo.operation_id.name if wo.operation_id else ""),
        ]
        for idx, label in enumerate(ORDER, start=1):
            needle = _norm(label)
            if any(needle in val for val in values):
                return idx
        return 999

    def _get_active_fma_workorders(self):
        self.ensure_one()
        return self.workorder_ids.filtered(lambda w: w.state not in ("done", "cancel", "progress"))

    def _reset_workorder_dependencies(self, ordered_wos):
        if not ordered_wos:
            return

        wo_model = self.env["mrp.workorder"]
        fields_map = wo_model._fields

        # Reset all known dependency representations first to avoid cycles.
        if "blocked_by_workorder_ids" in fields_map:
            ordered_wos.write({"blocked_by_workorder_ids": [(5, 0, 0)]})

        if "next_work_order_id" in fields_map:
            ordered_wos.write({"next_work_order_id": False})

        # Rebuild a clean chain WO1 -> WO2 -> WO3...
        previous = False
        for wo in ordered_wos:
            values = {}
            if previous:
                if "blocked_by_workorder_ids" in fields_map:
                    values["blocked_by_workorder_ids"] = [(4, previous.id)]
                if "prev_work_order_id" in fields_map:
                    values["prev_work_order_id"] = previous.id
            if values:
                wo.write(values)

            if previous and "next_work_order_id" in fields_map:
                previous.write({"next_work_order_id": wo.id})

            previous = wo

    def _run_local_replan(self):
        self.ensure_one()

        # Try the local / lightweight replanning methods first.
        for method_name in (
            "action_replan_workorders_backward",
            "action_replanifier",
            "action_replan_workorders",
            "button_replan",
        ):
            if hasattr(self, method_name):
                _logger.info("FMA resequence | MO=%s | local replan via %s", self.name, method_name)
                return getattr(self, method_name)()

        # Last fallback only if nothing else exists.
        if hasattr(self, "button_plan"):
            _logger.info("FMA resequence | MO=%s | fallback local replan via button_plan", self.name)
            return self.button_plan()
        return True

    def action_resequence_fma(self):
        for production in self:
            active_wos = production._get_active_fma_workorders()
            changed = False

            # Update the real business sequence used by the existing planning engine.
            for wo in active_wos:
                rank = production._fma_rank(wo)
                if rank < 999 and wo.operation_id:
                    new_seq = rank * 10
                    if wo.operation_id.sequence != new_seq:
                        wo.operation_id.sequence = new_seq
                        changed = True

            ordered_wos = active_wos.sorted(key=lambda wo: ((wo.op_sequence or 0), wo.id))
            production._reset_workorder_dependencies(ordered_wos)

            _logger.info(
                "FMA resequence | MO=%s | changed=%s | ordered=%s",
                production.name,
                changed,
                [(wo.id, wo.name, wo.op_sequence) for wo in ordered_wos],
            )

            production._run_local_replan()

        return True
