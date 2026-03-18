# -*- coding: utf-8 -*-
import json
from odoo import fields, models


class MrpReplanPreviewWizard(models.TransientModel):
    _name = 'mrp.replan.preview.wizard'
    _description = 'Prévisualisation du recalcul OF'

    production_id = fields.Many2one(
        'mrp.production',
        string='Ordre de fabrication',
        required=True,
        readonly=True,
    )
    summary_html = fields.Html(
        string='Résumé',
        sanitize=False,
        readonly=True,
    )
    preview_json = fields.Text(
        string='Données techniques',
        readonly=True,
    )

    def action_confirm(self):
        self.ensure_one()
        payload = json.loads(self.preview_json or '{}')
        self.production_id.action_apply_replan_preview(payload)
        return {'type': 'ir.actions.act_window_close'}
