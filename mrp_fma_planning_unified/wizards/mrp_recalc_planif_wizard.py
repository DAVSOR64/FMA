from odoo import api, fields, models
from odoo.exceptions import ValidationError

class MrpRecalcPlanifWizard(models.TransientModel):
    _name = "mrp.recalc.planif.wizard"
    _description = "Wizard recalcul planification"

    production_id = fields.Many2one("mrp.production", required=True)
    delivery_date = fields.Datetime(string="Date livraison", readonly=True)
    of_finish_date = fields.Datetime(string="Date fin OF", readonly=True)
    computed_start_date = fields.Datetime(string="Début fabrication recalculé", readonly=True)
    po_html = fields.Html(string="PO associées", sanitize=False, readonly=True)
    info_html = fields.Html(string="Synthèse", sanitize=False, readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        prod = self.env["mrp.production"].browse(self.env.context.get("default_production_id"))
        if prod:
            ok, error = prod._check_delivery_vs_finish()
            if not ok:
                raise ValidationError(error)

            # Use currently saved values on the OF
            finish = prod._get_of_finish_date()
            delivery = prod._get_delivery_date()
            pos = prod._find_related_purchase_orders()

            # We compute a preview by reading existing workorders after last saved plan.
            wos = prod.workorder_ids.filtered(lambda w: w.state not in ("done", "cancel")).sorted(key=lambda w: ((w.op_sequence or 0), w.id))
            start_dt = wos[:1].macro_planned_start if wos[:1] and "macro_planned_start" in wos._fields else False

            rows = []
            for po in pos:
                supplier = po.partner_id.display_name if po.partner_id else ""
                planned = getattr(po, "date_planned", False) or getattr(po, "date_order", False) or ""
                rows.append(
                    "<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                        po.name or "",
                        supplier,
                        planned or "",
                    )
                )
            po_html = (
                "<table class='table table-sm table-bordered'>"
                "<thead><tr><th>PO</th><th>Fournisseur</th><th>Date prévue</th></tr></thead>"
                "<tbody>%s</tbody></table>" % ("".join(rows) or "<tr><td colspan='3'>Aucune PO liée trouvée.</td></tr>")
            )

            info_html = (
                "<table class='table table-sm table-bordered'>"
                "<tbody>"
                "<tr><th>Date livraison</th><td>%s</td></tr>"
                "<tr><th>Date fin OF</th><td>%s</td></tr>"
                "<tr><th>Début fabrication recalculé</th><td>%s</td></tr>"
                "</tbody></table>"
            ) % (delivery or "", finish or "", start_dt or "")

            res.update({
                "delivery_date": delivery,
                "of_finish_date": finish,
                "computed_start_date": start_dt,
                "po_html": po_html,
                "info_html": info_html,
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
