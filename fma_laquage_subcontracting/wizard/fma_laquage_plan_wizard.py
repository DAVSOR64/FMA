# -*- coding: utf-8 -*-
from odoo import models, fields, api


class FmaLaquagePlanWizard(models.TransientModel):
    _name = 'fma.laquage.plan.wizard'
    _description = 'Assistant planification laquage'

    production_id = fields.Many2one('mrp.production', required=True, readonly=True)
    subcontractor_id = fields.Many2one(
        'res.partner',
        string='Sous-traitant',
        required=True,
        domain=[('is_laquage_supplier', '=', True)],
    )
    create_purchase = fields.Boolean(string='Créer / vérifier l’achat', default=True)
    replan_now = fields.Boolean(string='Replanifier immédiatement', default=True)

    def action_apply(self):
        self.ensure_one()
        mo = self.production_id
        # Le poste est fixe : Laquage F2M. L'opérateur choisit uniquement le laqueur.
        # Le créneau est déterminé automatiquement par le rétroplanning.
        wo = mo._ensure_laquage_workorder()
        wo.write({'is_external_laquage': True, 'laquage_state': 'to_plan'})
        mo.write({
            'laquage_required': True,
            'laquage_subcontractor_id': self.subcontractor_id.id,
            'laquage_slot_id': False,
            'laquage_state': 'to_plan',
        })
        if self.replan_now:
            mo.action_replanifier_laquage()
        elif self.create_purchase:
            mo._ensure_laquage_purchase()
        return {'type': 'ir.actions.act_window_close'}
