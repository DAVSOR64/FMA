from odoo import api, fields, models
from odoo.exceptions import ValidationError

class MrpRecalcPlanifWizard(models.TransientModel):
    _name = "mrp.recalc.planif.wizard"
    _description = "Wizard recalcul planification"

    production_id = fields.Many2one("mrp.production", required=True)
    delivery_date = fields.Datetime(string="Date livraison", readonly=True)
    of_finish_date = fields.Datetime(string="Date fin OF", readonly=True)
    po_info = fields.Text(string="PO liées", readonly=True)
    warning_message = fields.Text(string="Avertissement", readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        prod = self.env["mrp.production"].browse(self.env.context.get("default_production_id"))
        if prod:
            delivery = prod._get_delivery_date()
            finish = prod._get_of_finish_date()
            pos = prod._find_related_purchase_orders()
            lines = []
            for po in pos:
                supplier = getattr(po.partner_id, "display_name", "") or ""
                planned = getattr(po, "date_planned", False) or getattr(po, "date_order", False) or ""
                lines.append("%s | %s | %s" % (po.name or "", supplier, planned))
            ok, error = prod._check_delivery_vs_finish()
            res.update({
                "delivery_date": delivery,
                "of_finish_date": finish,
                "po_info": "\n".join(lines) if lines else "Aucune PO liée trouvée.",
                "warning_message": error or "",
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
