# -*- coding: utf-8 -*-

from odoo import models, fields, api


class RecomputeQtyWizard(models.TransientModel):
    _name = 'stock.move.qty.recompute.wizard'
    _description = 'Recalcul quantités avant/après mouvements de stock'

    info = fields.Char(
        string='Information',
        default='Ce traitement va recalculer les quantités avant/après sur tout '
                'l\'historique des mouvements de stock. Cela peut prendre plusieurs '
                'minutes selon le volume de données.',
        readonly=True,
    )

    def action_recompute(self):
        self.ensure_one()
        self.env['stock.move.line'].recompute_all_history()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Recalcul terminé',
                'message': 'Les quantités avant/après ont été recalculées sur tout l\'historique.',
                'type': 'success',
                'sticky': False,
            },
        }
