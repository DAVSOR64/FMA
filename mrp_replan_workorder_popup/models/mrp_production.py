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

        # SNAPSHOT COMPLET : macro + dates Odoo
        snapshot = {}
        for wo in workorders:
            snapshot[wo.id] = {
                "macro_start": getattr(wo, "macro_planned_start", False),
                "date_start": getattr(wo, "date_start", False),
                "date_finished": getattr(wo, "date_finished", False),
            }

        mo_start_snapshot = self.date_start
        mo_finished_snapshot = getattr(self, "date_finished", False)
        mo_deadline_snapshot = getattr(self, "date_deadline", False)

        picking = self.picking_ids.filtered(lambda p: p.state not in ("done", "cancel"))[:1]
        picking_sched_snapshot = picking.scheduled_date if picking else False
        picking_deadline_snapshot = picking.date_deadline if picking else False

        # Important : on pousse la durée utilisée par ton moteur
        for wo in workorders:
            if "duration_expected" in wo._fields and "duration" in wo._fields:
                if wo.duration and wo.duration_expected != wo.duration:
                    wo.duration_expected = wo.duration

        # CALCUL RÉEL via ton moteur historique
        ctx = self.with_context(skip_macro_recalc=True)
        ctx._recalculate_macro_backward(workorders, end_dt=fixed_end_dt)
        ctx.apply_macro_to_workorders_dates()
        ctx._update_mo_dates_from_macro(forced_end_dt=fixed_end_dt)
        ctx._update_components_picking_dates()

        # Lecture du résultat simulé
        new_start = self.date_start
        transfer_date = picking.scheduled_date if picking else False

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

        # RESTORE COMPLET : on remet aussi les macros
        for wo in workorders:
            data = snapshot[wo.id]
            vals = {}
            if "macro_planned_start" in wo._fields:
                vals["macro_planned_start"] = data["macro_start"]
            if "date_start" in wo._fields:
                vals["date_start"] = data["date_start"]
            if "date_finished" in wo._fields:
                vals["date_finished"] = data["date_finished"]
            if vals:
                wo.with_context(skip_macro_recalc=True, skip_shift_chain=True, mail_notrack=True).write(vals)

        vals_mo = {}
        if "date_start" in self._fields:
            vals_mo["date_start"] = mo_start_snapshot
        if "date_finished" in self._fields:
            vals_mo["date_finished"] = mo_finished_snapshot
        if "date_deadline" in self._fields:
            vals_mo["date_deadline"] = mo_deadline_snapshot
        if vals_mo:
            self.with_context(skip_macro_recalc=True, mail_notrack=True).write(vals_mo)

        if picking:
            picking.with_context(mail_notrack=True).write({
                "scheduled_date": picking_sched_snapshot,
                "date_deadline": picking_deadline_snapshot,
            })

        return {
            "production_name": self.display_name or self.name or "",
            "date_start": fields.Datetime.to_string(new_start) if new_start else "",
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