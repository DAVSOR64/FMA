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

    def _build_replan_preview_payload(self):
        self.ensure_one()

        fixed_end_dt = (
            getattr(self, "macro_forced_end", False)
            or self.date_deadline
            or self.date_finished
            or getattr(self, "date_planned_finished", False)
        )
        if not fixed_end_dt:
            raise UserError(_("Aucune date de fin n'est définie sur l'OF."))

        # On ne modifie rien dans la preview : on montre l'état actuel + les PO liés.
        current_start = self.date_start or getattr(self, "date_planned_start", False)

        transfer_date = False
        picking = self.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))[:1]
        if picking:
            transfer_date = picking.scheduled_date

        purchase_orders = self.env["purchase.order"]
        if self.procurement_group_id:
            po_lines = self.env["purchase.order.line"].search([
                ("move_dest_ids.group_id", "=", self.procurement_group_id.id),
            ])
            purchase_orders = po_lines.mapped("order_id")

        po_data = []
        for po in purchase_orders:
            po_data.append({
                "name": po.name or "",
                "partner": po.partner_id.display_name or "",
                "date_planned": fields.Datetime.to_string(po.date_planned) if po.date_planned else "",
            })

        return {
            "production_name": self.display_name or self.name or "",
            "date_start": fields.Datetime.to_string(current_start) if current_start else "",
            "date_end": fields.Datetime.to_string(fixed_end_dt) if fixed_end_dt else "",
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
            or self.date_finished
            or getattr(self, "date_planned_finished", False)
        )
        if not fixed_end_dt:
            raise UserError(_("Aucune date de fin n'est définie sur l'OF."))

        ctx_self = self.with_context(skip_macro_recalc=True)

        if hasattr(ctx_self, "_recalculate_macro_backward"):
            ctx_self._recalculate_macro_backward(workorders, end_dt=fixed_end_dt)
        else:
            raise UserError(_("Méthode _recalculate_macro_backward introuvable dans mrp_replan_workorder."))

        if hasattr(ctx_self, "apply_macro_to_workorders_dates"):
            ctx_self.apply_macro_to_workorders_dates()

        if hasattr(ctx_self, "_update_mo_dates_from_macro"):
            ctx_self._update_mo_dates_from_macro(forced_end_dt=fixed_end_dt)

        if hasattr(ctx_self, "_update_components_picking_dates"):
            ctx_self._update_components_picking_dates()

        if hasattr(ctx_self, "_check_delivery_date_exceeded"):
            ctx_self._check_delivery_date_exceeded()

        po_text = "Aucun PO lié"
        if self.procurement_group_id:
            po_lines = self.env["purchase.order.line"].search([
                ("move_dest_ids.group_id", "=", self.procurement_group_id.id),
            ])
            purchase_orders = po_lines.mapped("order_id")
            if purchase_orders:
                po_text = ", ".join(
                    "%s - %s (%s)" % (
                        po.name or "",
                        po.partner_id.display_name or "",
                        fields.Datetime.to_string(po.date_planned) if po.date_planned else "-"
                    )
                    for po in purchase_orders
                )

        message = _(
            "Replanification effectuée\n"
            "Début fabrication : %s\n"
            "Fin fabrication : %s\n"
            "PO liés : %s"
        ) % (
            self.date_start or getattr(self, "date_planned_start", False) or "-",
            fixed_end_dt or "-",
            po_text,
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Planning recalculé"),
                "message": message,
                "type": "success",
                "sticky": True,
            }
        }

    def action_replan_operations(self):
        return self.action_open_replan_preview()
