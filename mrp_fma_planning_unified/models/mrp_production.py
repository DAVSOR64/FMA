
from odoo import api, models, fields as odoo_fields
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

FMA_ORDER = [
    "Débit FMA",
    "CU (banc) FMA",
    "Usinage FMA",
    "Montage FMA",
    "Vitrage FMA",
    "Emballage FMA",
]

CRON_LOCK_KEY = 947251


def _norm(value):
    return (value or "").strip().lower()


def _as_text(value):
    if not value:
        return ""
    if hasattr(value, "display_name"):
        return value.display_name or ""
    return str(value)


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def _post_planif_message(self, message):
        for rec in self:
            if hasattr(rec, "message_post"):
                rec.message_post(body=message)

    def _find_finish_custom_field(self):
        self.ensure_one()
        candidates = [
            "x_studio_date_de_fin",
            "x_studio_date_de_Fin",
            "x_studio_date_de_fin_1",
            "x_de_fin",
        ]
        for name in candidates:
            if name in self._fields:
                return name
        for name in self._fields:
            lowered = name.lower()
            if lowered.startswith("x_studio") and "date" in lowered and "fin" in lowered:
                return name
        return False

    def _read_custom_finish_value(self):
        self.ensure_one()
        field_name = self._find_finish_custom_field()
        return getattr(self, field_name) if field_name else False

    def _sync_finish_date_to_engine_fields(self):
        """Push custom finish date into fields already used by older planning modules."""
        for rec in self:
            finish_value = rec._read_custom_finish_value()
            if not finish_value:
                continue
            vals = {}
            if "x_de_fin" in rec._fields:
                vals["x_de_fin"] = finish_value
            if "macro_forced_end" in rec._fields:
                vals["macro_forced_end"] = finish_value
            if vals:
                super(MrpProduction, rec).write(vals)

    def write(self, vals):
        finish_field = False
        for rec in self[:1]:
            finish_field = rec._find_finish_custom_field()
            break

        finish_in_vals = finish_field and finish_field in vals
        finish_val = vals.get(finish_field) if finish_in_vals else None

        # Save the custom finish date without triggering the historical auto-replan chain.
        if finish_in_vals:
            other_vals = dict(vals)
            other_vals.pop(finish_field, None)
            res = super().write(other_vals) if other_vals else True
            column = self._fields[finish_field].column_type and finish_field or finish_field
            query = 'UPDATE mrp_production SET "%s" = %%s WHERE id IN %%s' % finish_field
            self.env.cr.execute(query, [finish_val, tuple(self.ids)])
            self.invalidate_recordset([finish_field])
            return res

        return super().write(vals)

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
        sale = False
        if "sale_id" in self._fields and self.sale_id:
            sale = self.sale_id
        if not sale and "procurement_group_id" in self._fields and self.procurement_group_id:
            sale = self.env["sale.order"].search([("procurement_group_id", "=", self.procurement_group_id.id)], limit=1)
        if not sale and self.origin:
            sale = self.env["sale.order"].search([("name", "=", self.origin)], limit=1)
        if not sale and "x_studio_mtn_mrp_sale_order" in self._fields:
            mtn_text = _as_text(self.x_studio_mtn_mrp_sale_order)
            if mtn_text:
                sale = self.env["sale.order"].search([("name", "=", mtn_text)], limit=1)
        return sale

    def _get_delivery_date(self):
        self.ensure_one()
        sale = self._get_sale_for_macro()
        if sale:
            for field_name in ("x_studio_date_livraison", "commitment_date", "expected_date", "effective_date"):
                if field_name in sale._fields and getattr(sale, field_name):
                    return getattr(sale, field_name)
        return False

    def _get_effective_finish_source(self):
        self.ensure_one()
        custom = self._read_custom_finish_value()
        if custom:
            return custom
        for field_name in ("x_de_fin", "macro_forced_end", "date_deadline", "date_finished"):
            if field_name in self._fields and getattr(self, field_name):
                return getattr(self, field_name)
        return False

    def _get_of_finish_date(self):
        self.ensure_one()
        if "date_finished" in self._fields and self.date_finished:
            return self.date_finished
        if "date_deadline" in self._fields and self.date_deadline:
            return self.date_deadline
        return self._get_effective_finish_source()

    def _get_preview_start_date(self):
        self.ensure_one()
        starts = []
        for wo in self.workorder_ids.filtered(lambda w: w.state not in ("done", "cancel")):
            for fname in ("macro_planned_start", "date_start"):
                if fname in wo._fields and getattr(wo, fname):
                    starts.append(getattr(wo, fname))
                    break
        return min(starts) if starts else False

    def _to_date_only(self, value):
        if not value:
            return False
        return odoo_fields.Date.to_date(value)

    def _find_related_purchase_orders(self):
        self.ensure_one()
        PurchaseOrder = self.env["purchase.order"]
        POL = self.env["purchase.order.line"]
        pos = PurchaseOrder.browse()

        group = getattr(self, "procurement_group_id", False)
        if group:
            pos |= POL.search([("move_dest_ids.group_id", "=", group.id)]).mapped("order_id")
            if "group_id" in PurchaseOrder._fields:
                pos |= PurchaseOrder.search([("group_id", "=", group.id)])

        sale = self._get_sale_for_macro()
        sale_name = sale.name if sale else ""
        if sale_name:
            if "origin" in PurchaseOrder._fields:
                pos |= PurchaseOrder.search([("origin", "ilike", sale_name)])
            if "partner_ref" in PurchaseOrder._fields:
                pos |= PurchaseOrder.search([("partner_ref", "ilike", sale_name)])

        origin_text = _as_text(self.origin)
        if origin_text and "origin" in PurchaseOrder._fields:
            pos |= PurchaseOrder.search([("origin", "ilike", origin_text)])

        if "x_studio_mtn_mrp_sale_order" in self._fields and "origin" in PurchaseOrder._fields:
            mtn_text = _as_text(self.x_studio_mtn_mrp_sale_order)
            if mtn_text:
                pos |= PurchaseOrder.search([("origin", "ilike", mtn_text)])

        return pos.sorted(lambda po: (po.date_order or po.create_date or po.id))

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
        active_wos = self._get_fma_workorders()
        for wo in active_wos:
            rank = self._fma_rank(wo)
            if rank < 999 and wo.operation_id:
                wo.operation_id.sequence = rank * 10
        ordered_wos = active_wos.sorted(key=lambda wo: ((wo.op_sequence or 0), wo.id))
        self._reset_workorder_dependencies(ordered_wos)
        return True

    def _check_delivery_vs_finish(self):
        self.ensure_one()
        delivery_dt = self._get_delivery_date()
        finish_dt = self._get_effective_finish_source()
        delivery_date = self._to_date_only(delivery_dt)
        finish_date = self._to_date_only(finish_dt)
        if delivery_date and finish_date and finish_date > delivery_date:
            raise ValidationError(
                "Impossible : la date de fin de fabrication (%s) est postérieure à la date de livraison promise (%s)."
                % (
                    odoo_fields.Date.to_string(finish_date),
                    odoo_fields.Date.to_string(delivery_date),
                )
            )
        return True

    def _recompute_single_macro_planning(self):
        self.ensure_one()
        self._check_delivery_vs_finish()
        self._sync_finish_date_to_engine_fields()

        sale = self._get_sale_for_macro()
        if hasattr(self, "compute_macro_schedule_from_sale") and sale:
            result = self.compute_macro_schedule_from_sale(sale)
        else:
            result = True
            for method_name in (
                "action_apply_replan_preview",
                "_apply_replan_real",
                "action_replan_workorders_backward",
                "action_replanifier",
                "action_replan_workorders",
                "button_replan",
            ):
                if hasattr(self, method_name):
                    result = getattr(self, method_name)()
                    break

        delivery = self._get_delivery_date()
        finish = self._get_of_finish_date()
        start = self._get_preview_start_date()
        po_count = len(self._find_related_purchase_orders())
        self._post_planif_message(
            "<b>Recalcul planification FMA</b><br/>"
            "Date livraison : %s<br/>"
            "Date début OF recalculée : %s<br/>"
            "Date fin OF recalculée : %s<br/>"
            "PO liées trouvées : %s" % (delivery or "-", start or "-", finish or "-", po_count)
        )
        return result

    def _preview_recompute_values(self):
        self.ensure_one()
        self._check_delivery_vs_finish()

        registry = self.env.registry
        with registry.cursor() as cr:
            env2 = api.Environment(cr, self.env.uid, dict(self.env.context))
            prod2 = env2[self._name].browse(self.id)
            prod2._sync_finish_date_to_engine_fields()
            prod2._resequence_fma_workorders()
            prod2._recompute_single_macro_planning()

            preview = {
                "delivery_date": prod2._get_delivery_date(),
                "of_finish_date": prod2._get_of_finish_date(),
                "of_start_date": prod2._get_preview_start_date(),
                "purchase_orders": [],
            }
            for po in prod2._find_related_purchase_orders():
                preview["purchase_orders"].append({
                    "name": po.name or "",
                    "supplier": po.partner_id.display_name if po.partner_id else "",
                    "planned": getattr(po, "date_planned", False) or getattr(po, "date_order", False) or "",
                })
            cr.rollback()
        return preview

    def action_open_recalc_planif_popup(self):
        self.ensure_one()
        self._check_delivery_vs_finish()
        return {
            "type": "ir.actions.act_window",
            "name": "Recalcul planification",
            "res_model": "mrp.recalc.planif.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_production_id": self.id},
        }

    def action_resequence_fma(self):
        for production in self:
            production._resequence_fma_workorders()
            production._post_planif_message("<b>Réordonnancement FMA appliqué</b>")
        return True

    def _acquire_cron_lock(self):
        self.env.cr.execute("SELECT pg_try_advisory_lock(%s)", (CRON_LOCK_KEY,))
        return bool(self.env.cr.fetchone()[0])

    def _release_cron_lock(self):
        self.env.cr.execute("SELECT pg_advisory_unlock(%s)", (CRON_LOCK_KEY,))

    @api.model
    def action_batch_resequence_and_recompute_non_started(self):
        mos = self.search([("state", "not in", ("done", "cancel"))])
        treated = skipped = errors = 0
        for mo in mos:
            if not mo._is_non_started_for_fma_batch():
                skipped += 1
                continue
            try:
                with self.env.cr.savepoint():
                    mo._check_delivery_vs_finish()
                    mo._sync_finish_date_to_engine_fields()
                    mo._resequence_fma_workorders()
                    mo._recompute_single_macro_planning()
                    mo._post_planif_message("<b>Traitement batch FMA</b><br/>Succès.")
                    treated += 1
            except Exception as e:
                errors += 1
                _logger.warning("FMA batch error on %s: %s", mo.display_name, e)
                try:
                    with self.env.cr.savepoint():
                        mo._post_planif_message("<b>Traitement batch FMA</b><br/>Erreur : %s" % e)
                except Exception:
                    _logger.warning("Impossible d'écrire le message chatter sur %s", mo.display_name)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Recalcul FMA terminé",
                "message": "OF traités : %s | ignorés : %s | erreurs : %s" % (treated, skipped, errors),
                "type": "success" if not errors else "warning",
                "sticky": False,
            },
        }

    @api.model
    def cron_batch_resequence_and_recompute_non_started(self):
        if not self._acquire_cron_lock():
            _logger.info("FMA cron skipped: another run is active.")
            return True
        try:
            return self.action_batch_resequence_and_recompute_non_started()
        finally:
            self._release_cron_lock()
