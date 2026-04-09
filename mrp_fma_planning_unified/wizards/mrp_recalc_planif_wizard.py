
from odoo import api, fields, models
from odoo.exceptions import ValidationError

class MrpRecalcPlanifWizard(models.TransientModel):
    _name = "mrp.recalc.planif.wizard"
    _description = "Wizard recalcul planification"

    production_id = fields.Many2one("mrp.production", required=True)
    preview_html = fields.Html(string="Prévisualisation", sanitize=False, readonly=True)
    po_html = fields.Html(string="PO associées", sanitize=False, readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        prod = self.env["mrp.production"].browse(self.env.context.get("default_production_id"))
        if prod:
            ok, error = prod._check_delivery_vs_finish()
            if not ok:
                raise ValidationError(error)

            preview = prod._preview_recompute_values()
            delivery = preview.get("delivery_date") or ""
            finish = preview.get("of_finish_date") or ""
            start = preview.get("of_start_date") or ""

            preview_html = (
                "<div style='width:100%;'>"
                "<table style='width:100%; border-collapse:collapse;'>"
                "<tr>"
                "<td style='width:38%; padding:8px; border:1px solid #d9d9d9; background:#f6f6f6; font-weight:600;'>Date livraison</td>"
                "<td style='width:62%; padding:8px; border:1px solid #d9d9d9;'>%s</td>"
                "</tr>"
                "<tr>"
                "<td style='padding:8px; border:1px solid #d9d9d9; background:#f6f6f6; font-weight:600;'>Nouvelle date début OF</td>"
                "<td style='padding:8px; border:1px solid #d9d9d9;'>%s</td>"
                "</tr>"
                "<tr>"
                "<td style='padding:8px; border:1px solid #d9d9d9; background:#f6f6f6; font-weight:600;'>Nouvelle date fin OF</td>"
                "<td style='padding:8px; border:1px solid #d9d9d9;'>%s</td>"
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
                    "</tr>" % (po["name"], po["supplier"], po["planned"])
                )

            po_html = (
                "<div style='width:100%; margin-top:10px;'>"
                "<div style='font-weight:600; margin-bottom:8px;'>PO associées</div>"
                "<table style='width:100%; border-collapse:collapse;'>"
                "<thead>"
                "<tr>"
                "<th style='text-align:left; padding:8px; border:1px solid #d9d9d9; background:#f6f6f6;'>PO</th>"
                "<th style='text-align:left; padding:8px; border:1px solid #d9d9d9; background:#f6f6f6;'>Fournisseur</th>"
                "<th style='text-align:left; padding:8px; border:1px solid #d9d9d9; background:#f6f6f6;'>Date prévue</th>"
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
        ok, error = self.production_id._check_delivery_vs_finish()
        if not ok:
            raise ValidationError(error)
        self.production_id._resequence_fma_workorders()
        self.production_id._recompute_single_macro_planning()
        return {"type": "ir.actions.act_window_close"}
