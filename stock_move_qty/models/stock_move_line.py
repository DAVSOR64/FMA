# -*- coding: utf-8 -*-

from collections import defaultdict

from odoo import api, fields, models


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    qty_before_move = fields.Float(
        string='Qté avant mouvement',
        digits='Product Unit of Measure',
        readonly=True,
        copy=False,
    )
    qty_after_move = fields.Float(
        string='Qté après mouvement',
        digits='Product Unit of Measure',
        readonly=True,
        copy=False,
    )
    qty_tracked_location_id = fields.Many2one(
        'stock.location',
        string='Emplacement pris en compte',
        readonly=True,
        copy=False,
    )
    qty_move_direction = fields.Selection(
        [
            ('in', 'Entrée'),
            ('out', 'Sortie'),
            ('other', 'Autre'),
        ],
        string='Sens calcul',
        readonly=True,
        copy=False,
    )

    def _get_done_qty_in_product_uom(self):
        self.ensure_one()
        qty = 0.0
        if 'qty_done' in self._fields:
            qty = self.qty_done or 0.0
        elif 'quantity' in self._fields:
            qty = self.quantity or 0.0

        uom = False
        if 'product_uom_id' in self._fields:
            uom = self.product_uom_id
        if not uom and self.move_id:
            uom = self.move_id.product_uom

        if uom and self.product_id.uom_id and uom != self.product_id.uom_id:
            qty = uom._compute_quantity(qty, self.product_id.uom_id)
        return qty

    def _get_tracked_location_and_delta(self):
        """Retourne l'emplacement à suivre et l'impact stock.

        Règles métier demandées :
        - entrée vers un emplacement interne => on suit l'emplacement de destination
        - sortie depuis un emplacement interne => on suit l'emplacement source
        - transfert interne/interne => non calculé ici (une seule paire avant/après)
        """
        self.ensure_one()

        src = self.location_id
        dest = self.location_dest_id
        qty = self._get_done_qty_in_product_uom()

        if not self.product_id or not qty:
            return False, 0.0, 'other'

        src_internal = src.usage == 'internal' if src else False
        dest_internal = dest.usage == 'internal' if dest else False

        if dest_internal and not src_internal:
            return dest, qty, 'in'

        if src_internal and not dest_internal:
            return src, -qty, 'out'

        return False, 0.0, 'other'

    @api.model
    def recompute_all_history(self):
        lines = self.search(
            [('state', '=', 'done'), ('product_id', '!=', False)],
            order='date,id'
        )

        running_qty = defaultdict(float)
        to_write = []

        for line in lines:
            location, delta, direction = line._get_tracked_location_and_delta()
            vals = {
                'qty_before_move': 0.0,
                'qty_after_move': 0.0,
                'qty_tracked_location_id': False,
                'qty_move_direction': direction,
            }

            if location:
                key = (line.product_id.id, location.id)
                before = running_qty[key]
                after = before + delta
                running_qty[key] = after

                vals.update({
                    'qty_before_move': before,
                    'qty_after_move': after,
                    'qty_tracked_location_id': location.id,
                })

            to_write.append((line, vals))

        for line, vals in to_write:
            line.sudo().write(vals)

        return True
