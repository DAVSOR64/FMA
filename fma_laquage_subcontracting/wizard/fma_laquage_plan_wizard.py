# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class FmaLaquagePlanWizard(models.TransientModel):
    _name = 'fma.laquage.plan.wizard'
    _description = 'Assistant planification laquage'

    production_id = fields.Many2one('mrp.production', required=True, readonly=True)
    subcontractor_id = fields.Many2one('fma.laquage.subcontractor', string='Sous-traitant', required=True)
    slot_id = fields.Many2one('fma.laquage.slot', string='Créneau', required=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string='Poste laquage', help='Utilisé uniquement si l’opération laquage n’existe pas encore sur l’OF.')
    create_purchase = fields.Boolean(string='Créer / vérifier l’achat', default=True)
    replan_now = fields.Boolean(string='Replanifier immédiatement', default=True)

    @api.onchange('subcontractor_id')
    def _onchange_subcontractor_id(self):
        self.slot_id = False
        return {'domain': {'slot_id': [('subcontractor_id', '=', self.subcontractor_id.id), ('active', '=', True)]}}

    def action_apply(self):
        self.ensure_one()
        mo = self.production_id
        wo = mo._ensure_laquage_workorder(self.workcenter_id)
        wo.write({'is_external_laquage': True, 'laquage_state': 'to_plan'})
        mo.write({
            'laquage_required': True,
            'laquage_subcontractor_id': self.subcontractor_id.id,
            'laquage_slot_id': self.slot_id.id,
            'laquage_state': 'to_plan',
        })
        if self.replan_now:
            mo.action_replanifier_laquage()
        elif self.create_purchase:
            mo._ensure_laquage_purchase()
        return {'type': 'ir.actions.act_window_close'}
