from odoo import models, fields
import json


class MrpReplanPreviewWizard(models.TransientModel):
    _name = "mrp.replan.preview.wizard"
    _description = "Preview Replan"

    production_id = fields.Many2one("mrp.production")
    preview_json = fields.Text()
    summary_html = fields.Html()

    def action_confirm(self):
        self.ensure_one()
        payload = json.loads(self.preview_json or "{}")
        self.production_id.action_apply_replan_preview(payload)
        return {"type": "ir.actions.act_window_close"}
