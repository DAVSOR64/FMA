import json
from odoo import models, fields, _
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def action_open_replan_preview(self):
        self.ensure_one()

        workorders = self.workorder_ids.filtered(
            lambda w: w.state not in ("done", "cancel")
        )

        if not workorders:
            raise UserError(_("Aucune opération à recalculer"))

        # 🔥 SNAPSHOT
        snapshot = {
            "wo": {
                wo.id: {
                    "start": wo.date_planned_start,
                    "end": wo.date_planned_finished,
                }
                for wo in workorders
            },
            "mo_start": self.date_start,
        }

        fixed_end = (
            getattr(self, "macro_forced_end", False)
            or self.date_deadline
            or self.date_finished
            or self.date_planned_finished
        )

        # 🔥 CALCUL RÉEL (simulation)
        self._run_real_replan(fixed_end)

        # 🔥 LECTURE RESULTAT
        new_start = self.date_start

        # 🔥 RESTORE
        for wo in workorders:
            data = snapshot["wo"][wo.id]
            wo.date_planned_start = data["start"]
            wo.date_planned_finished = data["end"]

        self.date_start = snapshot["mo_start"]

        html = f"""
            <p><b>Début :</b> {new_start}</p>
            <p><b>Fin :</b> {fixed_end}</p>
        """

        wiz = self.env["mrp.replan.preview.wizard"].create({
            "production_id": self.id,
            "preview_json": json.dumps({"end": str(fixed_end)}),
            "summary_html": html,
        })

        return {
            "type": "ir.actions.act_window",
            "res_model": "mrp.replan.preview.wizard",
            "res_id": wiz.id,
            "view_mode": "form",
            "target": "new",
        }

    # 🔥 TON MOTEUR EXISTANT
    def _run_real_replan(self, fixed_end):
        workorders = self.workorder_ids.filtered(
            lambda w: w.state not in ("done", "cancel")
        )

        ctx = self.with_context(skip_macro_recalc=True)

        ctx._recalculate_macro_backward(workorders, end_dt=fixed_end)
        ctx.apply_macro_to_workorders_dates()
        ctx._update_mo_dates_from_macro(forced_end_dt=fixed_end)
        ctx._update_components_picking_dates()

    def _apply_replan_real(self, payload):
        fixed_end = (
            getattr(self, "macro_forced_end", False)
            or self.date_deadline
            or self.date_finished
            or self.date_planned_finished
        )

        self._run_real_replan(fixed_end)

    # alias studio
    def action_replan_operations(self):
        return self.action_open_replan_preview()