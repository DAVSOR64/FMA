# -*- coding: utf-8 -*-

from odoo import api, fields, models


class FmaLaquageReturnAlertWizard(models.TransientModel):
    _name = 'fma.laquage.return.alert.wizard'
    _description = 'Alerte retour laquage F2M'

    production_id = fields.Many2one('mrp.production', string='OF', required=True, readonly=True)
    message = fields.Text(string='Message', required=True, readonly=True)
    alert_type = fields.Selection([
        ('success', 'Conforme'),
        ('warning', 'Avance'),
        ('danger', 'Retard'),
    ], string='Type', default='success', readonly=True)

    def action_close_reload(self):
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_replanifier_of(self):
        self.ensure_one()
        production = self.production_id
        # On appelle le bouton de replanification existant si présent.
        # Le module FMA peut avoir plusieurs noms selon les versions.
        for method_name in (
            'action_replanifier',
            'action_replanifier_of',
            'action_open_replanification_wizard',
            'action_replanifier_production',
        ):
            if hasattr(production, method_name):
                action = getattr(production, method_name)()
                return action or {'type': 'ir.actions.client', 'tag': 'reload'}
        return {'type': 'ir.actions.client', 'tag': 'reload'}
