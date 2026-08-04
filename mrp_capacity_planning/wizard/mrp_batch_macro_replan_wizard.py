# -*- coding: utf-8 -*-
from odoo import fields, models


class MrpBatchMacroReplanWizard(models.TransientModel):
    _name = 'mrp.batch.macro.replan.wizard'
    _description = 'Wizard recalcul batch macro planning OF non démarrés'

    security_days = fields.Integer(string='Jours de sécurité', default=6, required=True)
    mo_count = fields.Integer(string='OF candidats', readonly=True)
    treated = fields.Integer(string='OF recalculés', readonly=True)
    skipped_started = fields.Integer(string='OF ignorés (déjà démarrés)', readonly=True)
    skipped_no_target = fields.Integer(string='OF ignorés (sans date cible)', readonly=True)
    error_count = fields.Integer(string='Erreurs', readonly=True)
    result_message = fields.Text(string='Résultat', readonly=True)

    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        productions = self.env['mrp.production'].search([
            ('state', 'in', ['confirmed', 'progress'])
        ])
        res['mo_count'] = len(productions)
        return res

    def action_run(self):
        self.ensure_one()
        result = self.env['mrp.production'].action_batch_recompute_macro_not_started(
            security_days=self.security_days,
        )
        self.write({
            'treated': result['treated'],
            'skipped_started': result['skipped_started'],
            'skipped_no_target': result['skipped_no_target'],
            'error_count': len(result['errors']),
            'result_message': result['message'] + (('\n\n' + '\n'.join(result['errors'])) if result['errors'] else ''),
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
