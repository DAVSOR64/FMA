# -*- coding: utf-8 -*-

from datetime import datetime, time, timedelta
from math import ceil

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    _FMA_CUSTOM_FINISH_FIELD = "x_studio_date_de_fin"

    # -------------------------------------------------------------------------
    # Helpers dates / lecture contexte métier
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

    def _fma_format_date(self, value):
        if not value:
            return ""
        if isinstance(value, datetime):
            return value.strftime("%d/%m/%Y")
        if hasattr(value, "strftime"):
            return value.strftime("%d/%m/%Y")
        return str(value)

    def _fma_get_sale_record(self):
        self.ensure_one()
        sale = False

        for field_name in ["sale_id", "x_sale_id"]:
            if field_name in self._fields and self[field_name]:
                sale = self[field_name]
                break

        if not sale and "x_studio_mtn_mrp_sale_order" in self._fields and self.x_studio_mtn_mrp_sale_order:
            raw = self.x_studio_mtn_mrp_sale_order
            if hasattr(raw, "_name") and raw._name == "sale.order":
                sale = raw
            else:
                sale_name = raw.display_name if hasattr(raw, "display_name") else str(raw)
                sale = self.env["sale.order"].search([("name", "=", sale_name)], limit=1)

        if not sale and getattr(self, "origin", False):
            sale = self.env["sale.order"].search([("name", "=", self.origin)], limit=1)

        return sale

    def _fma_get_delivery_dt(self):
        self.ensure_one()

        # Réutilise une éventuelle logique existante
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

        sale = self._fma_get_sale_record()
        if sale:
            for field_name in [
                "x_studio_date_livraison",
                "commitment_date",
                "delivery_date",
                "expected_date",
            ]:
                if field_name in sale._fields and sale[field_name]:
                    value = sale[field_name]
                    if isinstance(value, datetime):
                        return value
                    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
                        return datetime.combine(value, time(0, 0, 0))

        return False

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

        sale = self._fma_get_sale_record()
        candidates = [
            self.name,
            getattr(self, "origin", False),
        ]

        if sale:
            candidates.append(sale.name)

        if "x_studio_mtn_mrp_sale_order" in self._fields and self.x_studio_mtn_mrp_sale_order:
            raw = self.x_studio_mtn_mrp_sale_order
            candidates.append(raw.display_name if hasattr(raw, "display_name") else str(raw))

        for candidate in candidates:
            if candidate:
                pos |= PurchaseOrder.search([("origin", "ilike", str(candidate))])

        return pos.sorted(lambda p: (p.date_planned or p.date_order or fields.Datetime.now(), p.name or ""))

    # -------------------------------------------------------------------------
    # Helpers OT / calcul
    # -------------------------------------------------------------------------

    def _fma_get_workorders_for_replan(self):
        self.ensure_one()
        return self.workorder_ids.filtered(
            lambda w: w.state not in ("done", "cancel")
        ).sorted(
            key=lambda w: (
                getattr(w, "op_sequence", 0)
                or getattr(w.operation_id, "sequence", 0)
                or 0,
                w.id,
            )
        )

    def _fma_get_effective_hours(self, workorder):
        """
        Lit toujours les durées actuelles des OT.
        Si ta logique métier expose déjà une méthode spécifique, on la réutilise.
        """
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
        """
        Réutilise la logique existante si disponible.
        """
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

    def _fma_check_delivery_constraint(self, custom_finish_dt=None, delivery_dt=None):
        self.ensure_one()

        custom_finish_dt = custom_finish_dt or self._fma_get_custom_finish_dt()
        delivery_dt = delivery_dt or self._fma_get_delivery_dt()

        if delivery_dt and custom_finish_dt and custom_finish_dt.date() > delivery_dt.date():
            raise UserError(
                _(
                    "Impossible : la date de fin de fabrication (%s) est postérieure à la date de livraison promise (%s)."
                ) % (
                    self._fma_format_date(custom_finish_dt),
                    self._fma_format_date(delivery_dt),
                )
            )

    # -------------------------------------------------------------------------
    # MOTEUR UNIQUE
    # -------------------------------------------------------------------------

    def _fma_build_planning_result(self):
        """
        Moteur unique appelé par :
        - Replanifier (popup)
        - Valider
        - cron

        Toujours basé sur :
        - x_studio_date_de_fin
        - durées OT actuelles
        - ressources actuelles
        """
        self.ensure_one()

        # Relecture des valeurs actuelles
        self.invalidate_recordset()
        self.workorder_ids.invalidate_recordset()

        custom_finish_dt = self._fma_get_custom_finish_dt()
        if not custom_finish_dt:
            raise UserError(_("La date de fin de fabrication personnalisée n'est pas renseignée."))

        delivery_dt = self._fma_get_delivery_dt()
        self._fma_check_delivery_constraint(custom_finish_dt=custom_finish_dt, delivery_dt=delivery_dt)

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
                "duration_minutes": (
                    getattr(wo, "duration_expected", 0.0)
                    or getattr(wo, "duration", 0.0)
                    or 0.0
                ),
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

    def _fma_simulate_from_custom_finish_date(self):
        self.ensure_one()
        return self._fma_build_planning_result()

    def _fma_apply_simulation(self, simulation=None):
        self.ensure_one()

        if simulation is None:
            simulation = self._fma_build_planning_result()

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

        return simulation

    # -------------------------------------------------------------------------
    # Bouton manuel
    # -------------------------------------------------------------------------

    def action_open_recalc_planif_wizard(self):
        self.ensure_one()

        # Vérifie tout de suite la cohérence métier
        self._fma_build_planning_result()

        return {
            "type": "ir.actions.act_window",
            "name": _("Recalcul planification"),
            "res_model": "mrp.recalc.planif.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_production_id": self.id},
        }

    # -------------------------------------------------------------------------
    # Batch / cron
    # -------------------------------------------------------------------------

    @api.model
    def action_batch_resequence_and_recompute_non_started(self):
        productions = self.search([
            ("state", "in", ["draft", "confirmed", "planned", "progress"])
        ])

        for production in productions:
            try:
                active_wos = production.workorder_ids.filtered(
                    lambda w: w.state not in ("done", "progress", "cancel")
                )
                if not active_wos:
                    continue

                simulation = production._fma_build_planning_result()
                production._fma_apply_simulation(simulation)
            except Exception:
                continue

        return True

    @api.model
    def cron_batch_resequence_and_recompute_non_started(self):
        return self.action_batch_resequence_and_recompute_non_started()