# -*- coding: utf-8 -*-
import json
from odoo import models, fields, _
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def action_open_replan_preview(self):
        self.ensure_one()

        workorders = self.workorder_ids.filtered(lambda w: w.state not in ("done", "cancel"))
        if not workorders:
            raise UserError(_("Aucune opération à recalculer."))

        payload = self._build_replan_preview_payload()

        wiz = self.env["mrp.replan.preview.wizard"].create({
            "production_id": self.id,
            "preview_json": json.dumps(payload, default=str),
            "summary_html": self._render_replan_preview_html(payload),
        })

        return {
            "type": "ir.actions.act_window",
            "name": _("Prévisualisation replanification"),
            "res_model": "mrp.replan.preview.wizard",
            "res_id": wiz.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_replan_operations(self):
        return self.action_open_replan_preview()
    
    def _apply_replan_real(self, payload=None):
        return self.action_apply_replan_preview(payload)

    def _build_replan_preview_payload(self):
        self.ensure_one()

        workorders = self.workorder_ids.filtered(
            lambda w: w.state not in ("done", "cancel")
        )

        fixed_end_dt = (
            getattr(self, "macro_forced_end", False)
            or self.date_deadline
            or getattr(self, "date_finished", False)
            or getattr(self, "date_planned_finished", False)
        )

        if not fixed_end_dt:
            raise UserError(_("Aucune date de fin n'est définie sur l'OF."))

        # 🔥 SNAPSHOT
        snapshot = {}
        for wo in workorders:
            snapshot[wo.id] = {
                "start": getattr(wo, "macro_planned_start", False) or wo.date_start,
                "end": getattr(wo, "macro_planned_end", False) or wo.date_finished,
            }

        mo_start_snapshot = self.date_start

        # 🔥 IMPORTANT : synchro durée
        for wo in workorders:
            if hasattr(wo, "duration_expected") and hasattr(wo, "duration"):
                if wo.duration and wo.duration_expected != wo.duration:
                    wo.duration_expected = wo.duration

        # 🔥 CALCUL RÉEL
        ctx = self.with_context(skip_macro_recalc=True)

        ctx._recalculate_macro_backward(workorders, end_dt=fixed_end_dt)
        ctx.apply_macro_to_workorders_dates()
        ctx._update_mo_dates_from_macro(forced_end_dt=fixed_end_dt)
        ctx._update_components_picking_dates()

        new_start = self.date_start

        transfer_date = False
        picking = self.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))[:1]
        if picking:
            transfer_date = picking.scheduled_date

        # 🔥 RESTORE
        for wo in workorders:
            data = snapshot[wo.id]

            if hasattr(wo, "macro_planned_start"):
                wo.macro_planned_start = data["start"]
            else:
                wo.date_start = data["start"]

            if hasattr(wo, "macro_planned_end"):
                wo.macro_planned_end = data["end"]
            else:
                wo.date_finished = data["end"]

        self.date_start = mo_start_snapshot

        # 🔥 PO
        purchase_orders = self.env["purchase.order"]
        if self.procurement_group_id:
            po_lines = self.env["purchase.order.line"].search([
                ("move_dest_ids.group_id", "=", self.procurement_group_id.id),
            ])
            purchase_orders = po_lines.mapped("order_id")

        po_data = []
        for po in purchase_orders:
            po_data.append({
                "name": po.name,
                "partner": po.partner_id.display_name,
                "date_planned": fields.Datetime.to_string(po.date_planned) if po.date_planned else "",
            })

        return {
            "production_name": self.display_name,
            "date_start": fields.Datetime.to_string(new_start),
            "date_end": fields.Datetime.to_string(fixed_end_dt),
            "transfer_date": fields.Datetime.to_string(transfer_date) if transfer_date else "",
            "purchase_orders": po_data,
        }
    def _render_replan_preview_html(self, payload):
        po_rows = ""
        for po in payload.get("purchase_orders", []):
            po_rows += """
                <tr>
                    <td>{name}</td>
                    <td>{partner}</td>
                    <td>{date_planned}</td>
                </tr>
            """.format(
                name=po.get("name", "") or "",
                partner=po.get("partner", "") or "",
                date_planned=po.get("date_planned", "") or "",
            )

        if not po_rows:
            po_rows = '<tr><td colspan="3">Aucun PO lié</td></tr>'

        return """
            <div>
                <p><b>OF :</b> {production_name}</p>
                <p><b>Début fabrication :</b> {date_start}</p>
                <p><b>Fin fabrication :</b> {date_end}</p>
                <p><b>Date de transfert :</b> {transfer_date}</p>
                <br/>
                <b>PO liés</b>
                <table class="table table-sm table-bordered">
                    <thead>
                        <tr>
                            <th>PO</th>
                            <th>Fournisseur</th>
                            <th>Date prévue</th>
                        </tr>
                    </thead>
                    <tbody>
                        {po_rows}
                    </tbody>
                </table>
            </div>
        """.format(
            production_name=payload.get("production_name", "-") or "-",
            date_start=payload.get("date_start", "-") or "-",
            date_end=payload.get("date_end", "-") or "-",
            transfer_date=payload.get("transfer_date", "-") or "-",
            po_rows=po_rows,
        )

    def action_apply_replan_preview(self, payload=None):
        self.ensure_one()

        workorders = self.workorder_ids.filtered(lambda w: w.state not in ("done", "cancel"))
        if not workorders:
            raise UserError(_("Aucune opération à recalculer."))

        fixed_end_dt = (
            getattr(self, "macro_forced_end", False)
            or self.date_deadline
            or getattr(self, "date_finished", False)
            or getattr(self, "date_planned_finished", False)
        )
        if not fixed_end_dt:
            raise UserError(_("Aucune date de fin n'est définie sur l'OF."))

        # important : on synchronise la durée utilisée par le moteur
        for wo in workorders:
            if hasattr(wo, "duration_expected") and hasattr(wo, "duration"):
                if wo.duration and wo.duration_expected != wo.duration:
                    wo.duration_expected = wo.duration

        ctx = self.with_context(skip_macro_recalc=True)

        ctx._recalculate_macro_backward(workorders, end_dt=fixed_end_dt)
        ctx.apply_macro_to_workorders_dates()
        ctx._update_mo_dates_from_macro(forced_end_dt=fixed_end_dt)
        ctx._update_components_picking_dates()

        # sécurité : flush pour être sûr que l'UI relise les vraies valeurs
        self.flush_recordset()
        workorders.flush_recordset()

        return True


    def _apply_replan_real(self, payload=None):
        return self.action_apply_replan_preview(payload)