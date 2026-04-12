
from odoo import api, fields, models


class MrpRecalcPlanifWizard(models.TransientModel):
    _name = "mrp.recalc.planif.wizard"
    _description = "Wizard recalcul planification"

    production_id = fields.Many2one("mrp.production", required=True)
    preview_html = fields.Html(string="Prévisualisation", sanitize=False, readonly=True)
    po_html = fields.Html(string="PO associées", sanitize=False, readonly=True)

    def _fmt(self, value):
        if not value:
            return ""
        if hasattr(value, "strftime"):
            return value.strftime("%d/%m/%Y")
        return str(value)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        prod = self.env["mrp.production"].browse(self.env.context.get("default_production_id"))
        if prod:
            prod._check_delivery_vs_finish()
            preview = prod._preview_recompute_values()
            delivery = self._fmt(preview.get("delivery_date"))
            finish = self._fmt(preview.get("of_finish_date"))
            start = self._fmt(preview.get("of_start_date"))

            preview_html = (
                "<div style='width:100%%;'>"
                "<table style='width:100%%; border-collapse:collapse; table-layout:fixed;'>"
                "<tr>"
                "<td style='width:35%%; padding:10px; border:1px solid #d9d9d9; background:#f6f6f6; font-weight:600;'>Date livraison</td>"
                "<td style='width:65%%; padding:10px; border:1px solid #d9d9d9;'>%s</td>"
                "</tr>"
                "<tr>"
                "<td style='padding:10px; border:1px solid #d9d9d9; background:#f6f6f6; font-weight:600;'>Nouvelle date début OF</td>"
                "<td style='padding:10px; border:1px solid #d9d9d9;'>%s</td>"
                "</tr>"
                "<tr>"
                "<td style='padding:10px; border:1px solid #d9d9d9; background:#f6f6f6; font-weight:600;'>Nouvelle date fin OF</td>"
                "<td style='padding:10px; border:1px solid #d9d9d9;'>%s</td>"
                "</tr>"
                "</table>"
                "</div>"
            ) % (delivery, start, finish)

            rows = []
            for po in preview.get("purchase_orders", []):
                rows.append(
                    "<tr>"
                    "<td style='padding:8px; border:1px solid #d9d9d9;'>%s</td>"
                    "<td style='padding:8px; border:1px solid #d9d9d9;'>%s</td>"
                    "<td style='padding:8px; border:1px solid #d9d9d9;'>%s</td>"
                    "</tr>" % (po["name"], po["supplier"], self._fmt(po["planned"]))
                )

            po_html = (
                "<div style='width:100%%; margin-top:14px;'>"
                "<div style='font-weight:600; margin-bottom:8px;'>PO associées</div>"
                "<table style='width:100%%; border-collapse:collapse; table-layout:fixed;'>"
                "<thead>"
                "<tr>"
                "<th style='width:20%%; text-align:left; padding:8px; border:1px solid #d9d9d9; background:#f6f6f6;'>PO</th>"
                "<th style='width:30%%; text-align:left; padding:8px; border:1px solid #d9d9d9; background:#f6f6f6;'>Fournisseur</th>"
                "<th style='width:50%%; text-align:left; padding:8px; border:1px solid #d9d9d9; background:#f6f6f6;'>Date prévue</th>"
                "</tr>"
                "</thead>"
                "<tbody>%s</tbody></table></div>"
            ) % ("".join(rows) or "<tr><td colspan='3' style='padding:8px; border:1px solid #d9d9d9;'>Aucune PO liée trouvée.</td></tr>")

            res.update({
                "preview_html": preview_html,
                "po_html": po_html,
            })
        return res

    def action_apply(self):
        self.ensure_one()
        self.production_id._check_delivery_vs_finish()
        self.production_id._sync_finish_date_to_engine_fields()
        self.production_id._resequence_fma_workorders()
        self.production_id._recompute_single_macro_planning()
        return {"type": "ir.actions.act_window_close"}
