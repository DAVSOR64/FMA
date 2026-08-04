
# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import api, fields, models


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    x_move_type = fields.Selection(
        [('EN', 'Entrée'), ('SO', 'Sortie'), ('AU', 'Autre')],
        string='Type mouvement',
        compute='_compute_qty_move_metadata',
        store=True,
    )
    qty_tracked_location_id = fields.Many2one(
        'stock.location',
        string='Emplacement suivi',
        compute='_compute_qty_move_metadata',
        store=True,
    )
    qty_before_move = fields.Float(string='Qté avant', default=0.0, readonly=True, copy=False)
    qty_after_move = fields.Float(string='Qté après', default=0.0, readonly=True, copy=False)

    @api.depends('location_id', 'location_dest_id')
    def _compute_qty_move_metadata(self):
        for line in self:
            move_type, tracked_location = line._get_tracked_location_and_type()
            line.x_move_type = move_type
            line.qty_tracked_location_id = tracked_location

    def _get_tracked_location_and_type(self):
        self.ensure_one()
        src = self.location_id
        dest = self.location_dest_id
        src_internal = bool(src and src.usage == 'internal')
        dest_internal = bool(dest and dest.usage == 'internal')

        if dest_internal and not src_internal:
            return 'EN', dest.id
        if src_internal and not dest_internal:
            return 'SO', src.id
        if src_internal and dest_internal:
            # Pour les transferts internes, on suit le stock de la source.
            return 'SO', src.id
        return 'AU', False

    @api.model
    def recompute_all_history(self):
        MoveLine = self.sudo().with_context(active_test=False)

        # Reset global pour éviter les reliquats.
        all_lines = MoveLine.search([])
        if all_lines:
            all_lines.write({
                'qty_before_move': 0.0,
                'qty_after_move': 0.0,
            })
            all_lines._compute_qty_move_metadata()

        done_lines = MoveLine.search([
            ('state', '=', 'done'),
            ('product_id', '!=', False),
        ], order='date, id')

        balances = defaultdict(float)
        batch_updates = []

        for line in done_lines:
            move_type, tracked_location_id = line._get_tracked_location_and_type()
            qty = abs(line.quantity or 0.0)

            if move_type == 'AU' or not tracked_location_id or not qty:
                batch_updates.append((line.id, 0.0, 0.0))
                continue

            key = (line.product_id.id, tracked_location_id)
            before_qty = balances[key]
            after_qty = before_qty + qty if move_type == 'EN' else before_qty - qty
            balances[key] = after_qty
            batch_updates.append((line.id, before_qty, after_qty))

        for line_id, before_qty, after_qty in batch_updates:
            MoveLine.browse(line_id).write({
                'qty_before_move': before_qty,
                'qty_after_move': after_qty,
            })
        return True
