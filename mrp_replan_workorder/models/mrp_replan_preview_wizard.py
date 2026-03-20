
# -*- coding: utf-8 -*-
import json
from odoo import models, fields


class MrpReplanPreviewWizard(models.TransientModel):
    _name = 'mrp.replan.preview.wizard'
    _description = 'Prévisualisation replanification OF'

    production_id = fields.Many2one('mrp.production', required=True, readonly=True)
    summary_html = fields.Html(readonly=True, sanitize=False)
    preview_json = fields.Text(readonly=True)

    def action_confirm(self):
        self.ensure_one()
        payload = json.loads(self.preview_json or '{}')
        self.production_id.action_apply_replan_preview(payload)
        return {'type': 'ir.actions.act_window_close'}
