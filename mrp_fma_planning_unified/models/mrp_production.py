import logging
from odoo import api, models

_logger = logging.getLogger(__name__)

FMA_ORDER = [
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

    # --------------------------
    # Eligibility / target dates
    # --------------------------
    def _is_non_started_for_fma_batch(self):
        self.ensure_one()

        if self.state in ("done", "cancel"):
            return False

        for wo in self.workorder_ids:
            if wo.state in ("progress", "done", "cancel"):
                return False
            if getattr(wo, "qty_produced", 0):
                return False
            if getattr(wo, "duration", 0):
                return False
        return True

    def _get_sale_for_macro(self):
        self.ensure_one()
        sale = None

        if "sale_id" in self._fields and self.sale_id:
            sale = self.sale_id

        if not sale and "procurement_group_id" in self._fields and self.procurement_group_id:
            sale = self.env["sale.order"].search(
                [("procurement_group_id", "=", self.procurement_group_id.id)],
                limit=1,
            )

        if not sale and self.origin:
            sale = self.env["sale.order"].search([("name", "=", self.origin)], limit=1)

        if not sale and "x_studio_mtn_mrp_sale_order" in self._fields:
            mtn = self.x_studio_mtn_mrp_sale_order
            if mtn:
                sale = self.env["sale.order"].search([("name", "=", mtn)], limit=1)

        return sale

    def _get_macro_target_date(self):
        self.ensure_one()

        # OF custom finish dates first
        for field_name in (
            "x_de_fin",
            "macro_forced_end",
            "date_deadline",
            "date_finished",
        ):
            if field_name in self._fields and getattr(self, field_name):
                return getattr(self, field_name)

        sale = self._get_sale_for_macro()
        if sale:
            for field_name in (
                "x_studio_date_livraison",
                "commitment_date",
                "expected_date",
                "effective_date",
            ):
                if field_name in sale._fields and getattr(sale, field_name):
                    return getattr(sale, field_name)

        return False

    # --------------------------
    # FMA resequencing
    # --------------------------
    def _fma_rank(self, wo):
        values = [
            _norm(wo.name),
            _norm(wo.workcenter_id.name),
            _norm(wo.operation_id.name if wo.operation_id else ""),
        ]
        for idx, label in enumerate(FMA_ORDER, start=1):
            needle = _norm(label)
            if any(needle in val for val in values):
                return idx
        return 999

    def _get_fma_workorders(self):
        self.ensure_one()
        return self.workorder_ids.filtered(lambda w: w.state not in ("done", "cancel"))

    def _reset_workorder_dependencies(self, ordered_wos):
        if not ordered_wos:
            return

        fields_map = self.env["mrp.workorder"]._fields

        reset_vals = {}
        if "blocked_by_workorder_ids" in fields_map:
            reset_vals["blocked_by_workorder_ids"] = [(5, 0, 0)]
        if "prev_work_order_id" in fields_map:
            reset_vals["prev_work_order_id"] = False
        if "next_work_order_id" in fields_map:
            reset_vals["next_work_order_id"] = False
        if reset_vals:
            ordered_wos.write(reset_vals)

        previous = False
        for wo in ordered_wos:
            vals = {}
            if previous:
                if "blocked_by_workorder_ids" in fields_map:
                    vals["blocked_by_workorder_ids"] = [(4, previous.id)]
                if "prev_work_order_id" in fields_map:
                    vals["prev_work_order_id"] = previous.id
            if vals:
                wo.write(vals)
            if previous and "next_work_order_id" in fields_map:
                previous.write({"next_work_order_id": wo.id})
            previous = wo

    def _resequence_fma_workorders(self):
        self.ensure_one()

        changed = False
        active_wos = self._get_fma_workorders()

        for wo in active_wos:
            rank = self._fma_rank(wo)
            if rank < 999 and wo.operation_id:
                new_seq = rank * 10
                if wo.operation_id.sequence != new_seq:
                    wo.operation_id.sequence = new_seq
                    changed = True

        ordered_wos = active_wos.sorted(key=lambda wo: ((wo.op_sequence or 0), wo.id))
        self._reset_workorder_dependencies(ordered_wos)

        _logger.info(
            "FMA unified | MO=%s | changed=%s | ordered=%s",
            self.name,
            changed,
            [(wo.id, wo.name, wo.op_sequence) for wo in ordered_wos],
        )
        return changed

    # --------------------------
    # Macro recompute
    # --------------------------
    def _recompute_single_macro_planning(self):
        self.ensure_one()

        sale = self._get_sale_for_macro()
        target_dt = self._get_macro_target_date()

        # Delegate to the business logic already present in mrp_replan_workorder.
        if hasattr(self, "compute_macro_schedule_from_sale") and sale:
            _logger.info(
                "FMA unified | MO=%s | compute_macro_schedule_from_sale | sale=%s | target=%s",
                self.name, sale.name, target_dt
            )
            return self.compute_macro_schedule_from_sale(sale)

        # Fallbacks to preserve existing business logic if sale linkage is missing.
        for method_name in (
            "action_apply_replan_preview",
            "_apply_replan_real",
            "action_replan_workorders_backward",
            "action_replanifier",
            "action_replan_workorders",
            "button_replan",
        ):
            if hasattr(self, method_name):
                _logger.info("FMA unified | MO=%s | fallback macro replan via %s", self.name, method_name)
                return getattr(self, method_name)()

        return True

    # --------------------------
    # Actions
    # --------------------------
    def action_resequence_fma(self):
        for production in self:
            production._resequence_fma_workorders()
        return True

    def action_resequence_and_recompute_macro(self):
        for production in self:
            production._resequence_fma_workorders()
            production._recompute_single_macro_planning()
        return True

    @api.model
    def action_batch_resequence_and_recompute_non_started(self):
        domain = [("state", "not in", ("done", "cancel"))]
        mos = self.search(domain)

        treated = 0
        skipped = 0

        for mo in mos:
            if not mo._is_non_started_for_fma_batch():
                skipped += 1
                continue
            mo._resequence_fma_workorders()
            mo._recompute_single_macro_planning()
            treated += 1

        _logger.info(
            "FMA unified batch | treated=%s | skipped=%s",
            treated, skipped
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Recalcul FMA terminé",
                "message": "OF traités : %s | OF ignorés : %s" % (treated, skipped),
                "type": "success",
                "sticky": False,
            },
        }

    @api.model
    def cron_batch_resequence_and_recompute_non_started(self):
        _logger.info("FMA unified cron | start")
        self.action_batch_resequence_and_recompute_non_started()
        _logger.info("FMA unified cron | done")
        return True
