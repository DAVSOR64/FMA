from odoo import models, fields
import json


class MrpReplanPreviewWizard(models.TransientModel):
    _name = "mrp.replan.preview.wizard"
    _description = "Preview Replan"

    production_id = fields.Many2one("mrp.production")
    preview_json = fields.Text()
    summary_html = fields.Html()

    def action_confirm(self):
        payload = json.loads(self.preview_json or "{}")
        self.production_id._apply_replan_real(payload)
        return {"type": "ir.actions.act_window_close"}