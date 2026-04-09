# -*- coding: utf-8 -*-

from datetime import datetime, time, timedelta
from math import ceil

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    _FMA_CUSTOM_FINISH_FIELD = "x_studio_date_de_fin"

    # -------------------------------------------------------------------------
    # Helpers lecture dates
    # -------------------------------------------------------------------------

    def _fma_get_custom_finish_dt(self):
        self.ensure_one()
        field_name = self._FMA_CUSTOM_FINISH_FIELD
        if field_name not in self._fields:
            return False

        value = self[field_name]
        if not value:
            return False

        if isinstance(value, datetime):
            return value

        if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
            return datetime.combine(value, time(11, 0, 0))

        return False

    def _fma_get_delivery_dt(self):
        self.ensure_one()

        for method_name in [
            "_get_promised_delivery_date",
            "_get_delivery_date",
            "_get_planned_delivery_date",
        ]:
            if hasattr(self, method_name):
                try:
                    value = getattr(self, method_name)()
                    if value:
                        if isinstance(value, datetime):
                            return value
                        if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
                            return datetime.combine(value, time(0, 0, 0))
                except Exception:
                    pass

        sale = False
        for field_name in ["sale_id", "x_sale_id"]:
            if field_name in self._fields and self[field_name]:
                sale = self[field_name]
                break

        if not sale and "x_studio_mtn_mrp_sale_order" in self._fields and self.x_studio_mtn_mrp_sale_order:
            sale = self.env["sale.order"].search(
                [("name", "=", self.x_studio_mtn_mrp_sale_order)],
                limit=1,
            )

        if sale:
            for field_name in [
                "commitment_date",
                "delivery_date",
                "x_studio_date_livraison",
                "x_studio_delivery_date",
            ]:
                if field_name in sale._fields and sale[field_name]:
                    value = sale[field_name]
                    if isinstance(value, datetime):
                        return value
                    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
                        return datetime.combine(value, time(0, 0, 0))

        return False

    def _fma_format_date(self, value):
        if not value:
            return ""
        if isinstance(value, datetime):
            return value.strftime("%d/%m/%Y")
        if hasattr(value, "strftime"):
            return value.strftime("%d/%m/%Y")
        return str(value)

    # -------------------------------------------------------------------------
    # Helpers PO
    # -------------------------------------------------------------------------

    def _find_related_purchase_orders(self):
        self.ensure_one()
        PurchaseOrder = self.env["purchase.order"]
        pos = PurchaseOrder.browse()

        procurement_group = False
        for field_name in ["procurement_group_id", "group_id"]:
            if field_name in self._fields and self[field_name]:
                procurement_group = self[field_name]
                break

        if procurement_group and "group_id" in PurchaseOrder._fields:
            pos |= PurchaseOrder.search([("group_id", "=", procurement_group.id)])

        candidates = []
        for candidate in [
            self.name,
            getattr(self, "origin", False),
            getattr(self, "x_studio_mtn_mrp_sale_order", False),
        ]:
            if candidate:
                candidates.append(str(candidate))

        for candidate in candidates:
            pos |= PurchaseOrder.search([("origin", "ilike", candidate)])

        return pos.sorted(lambda p: (p.date_planned or fields.Datetime.now(), p.name or ""))

    # -------------------------------------------------------------------------
    # Helpers calcul backward simplifié
    # -------------------------------------------------------------------------

    def _fma_get_workorders_for_replan(self):
        self.ensure_one()
        return self.workorder_ids.filtered(lambda w: w.state not in ("done", "cancel")).sorted(
            key=lambda w: (
                getattr(w, "sequence", 0) or 0,
                getattr(w.operation_id, "sequence", 0) or 0,
                w.id,
            )
        )

    def _fma_get_effective_hours(self, workorder):
        for method_name in [
            "_get_effective_duration_hours_for_macro",
            "_get_effective_duration_hours",
            "_get_effective_workorder_duration_hours",
        ]:
            if hasattr(self, method_name):
                try:
                    value = getattr(self, method_name)(workorder)
                    if value is not None:
                        return max(float(value), 0.0)
                except Exception:
                    pass

        duration_minutes = (
            getattr(workorder, "duration_expected", 0.0)
            or getattr(workorder, "duration", 0.0)
            or 0.0
        )
        return max(float(duration_minutes) / 60.0, 0.0)

    def _fma_get_resources_count(self, workorder):
        for method_name in [
            "_get_number_of_resources_for_workorder",
            "_get_resource_count_for_workorder",
            "_get_workorder_resource_count",
        ]:
            if hasattr(self, method_name):
                try:
                    value = getattr(self, method_name)(workorder)
                    if value:
                        return max(int(value), 1)
                except Exception:
                    pass

        if "nb_resource" in workorder._fields and workorder.nb_resource:
            return max(int(workorder.nb_resource), 1)

        return 1

    def _fma_get_hours_per_day(self):
        return 7.5

    def _fma_previous_business_day(self, dt_value):
        dt_value = dt_value - timedelta(days=1)
        while dt_value.weekday() >= 5:
            dt_value -= timedelta(days=1)
        return dt_value

    def _fma_subtract_working_days(self, end_dt, nb_days):
        current = end_dt
        counted = 0
        while counted < nb_days - 1:
            current = self._fma_previous_business_day(current)
            counted += 1
        return current

    def _fma_simulate_from_custom_finish_date(self):
        self.ensure_one()

        custom_finish_dt = self._fma_get_custom_finish_dt()
        if not custom_finish_dt:
            raise UserError(_("La date de fin de fabrication personnalisée n'est pas renseignée."))

        delivery_dt = self._fma_get_delivery_dt()
        if delivery_dt and custom_finish_dt.date() > delivery_dt.date():
            raise UserError(
                _(
                    "Impossible : la date de fin de fabrication (%s) est postérieure à la date de livraison promise (%s)."
                )
                % (
                    self._fma_format_date(custom_finish_dt),
                    self._fma_format_date(delivery_dt),
                )
            )

        workorders = self._fma_get_workorders_for_replan()
        if not workorders:
            return {
                "delivery_dt": delivery_dt,
                "custom_finish_dt": custom_finish_dt,
                "new_start_dt": custom_finish_dt,
                "new_finish_dt": custom_finish_dt,
                "lines": [],
                "purchase_orders": self._find_related_purchase_orders(),
            }

        hours_per_day = self._fma_get_hours_per_day()
        current_finish_dt = custom_finish_dt
        simulated_lines = []

        for wo in reversed(workorders):
            effective_hours = self._fma_get_effective_hours(wo)
            resources = self._fma_get_resources_count(wo)
            effective_hours = effective_hours / max(resources, 1)

            nb_days = max(int(ceil(effective_hours / hours_per_day)), 1)
            macro_start_dt = self._fma_subtract_working_days(
                datetime.combine(current_finish_dt.date(), time(7, 30, 0)),
                nb_days,
            )
            macro_finish_dt = current_finish_dt

            simulated_lines.append({
                "workorder": wo,
                "macro_start_dt": macro_start_dt,
                "macro_finish_dt": macro_finish_dt,
                "effective_hours": effective_hours,
                "resources": resources,
            })

            previous_day = self._fma_previous_business_day(macro_start_dt)
            current_finish_dt = datetime.combine(previous_day.date(), time(11, 0, 0))

        simulated_lines.reverse()

        return {
            "delivery_dt": delivery_dt,
            "custom_finish_dt": custom_finish_dt,
            "new_start_dt": simulated_lines[0]["macro_start_dt"],
            "new_finish_dt": simulated_lines[-1]["macro_finish_dt"],
            "lines": simulated_lines,
            "purchase_orders": self._find_related_purchase_orders(),
        }

    def _fma_apply_simulation(self, simulation):
        self.ensure_one()

        vals = {}
        if "date_start" in self._fields and simulation.get("new_start_dt"):
            vals["date_start"] = simulation["new_start_dt"]
        if "date_finished" in self._fields and simulation.get("new_finish_dt"):
            vals["date_finished"] = simulation["new_finish_dt"]
        if "date_planned_start" in self._fields and simulation.get("new_start_dt"):
            vals["date_planned_start"] = simulation["new_start_dt"]

        if vals:
            super(MrpProduction, self).write(vals)

        for line in simulation.get("lines", []):
            wo = line["workorder"]
            wo_vals = {}

            if "macro_planned_start" in wo._fields:
                wo_vals["macro_planned_start"] = line["macro_start_dt"]
            if "date_start" in wo._fields:
                wo_vals["date_start"] = line["macro_start_dt"]
            if "date_finished" in wo._fields:
                wo_vals["date_finished"] = line["macro_finish_dt"]

            if wo_vals:
                wo.write(wo_vals)

    # -------------------------------------------------------------------------
    # Bouton wizard manuel
    # -------------------------------------------------------------------------

    def action_open_recalc_planif_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Recalcul planification"),
            "res_model": "mrp.recalc.planif.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_production_id": self.id,
            },
        }

    # -------------------------------------------------------------------------
    # Cron / batch
    # -------------------------------------------------------------------------

    @api.model
    def action_batch_resequence_and_recompute_non_started(self):
        domain = [("state", "in", ["draft", "confirmed", "planned", "progress"])]
        productions = self.search(domain)

        for production in productions:
            try:
                active_wos = production.workorder_ids.filtered(
                    lambda w: w.state not in ("done", "progress", "cancel")
                )
                if not active_wos:
                    continue

                simulation = production._fma_simulate_from_custom_finish_date()
                production._fma_apply_simulation(simulation)
            except UserError:
                continue
            except Exception:
                continue

        return True

    @api.model
    def cron_batch_resequence_and_recompute_non_started(self):
        return self.action_batch_resequence_and_recompute_non_started()
