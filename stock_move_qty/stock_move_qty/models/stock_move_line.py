# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    x_qty_before = fields.Float(
        string='Qté avant',
        digits='Product Unit of Measure',
        default=0.0,
        help='Quantité en stock sur l\'emplacement avant ce mouvement',
    )
    x_qty_after = fields.Float(
        string='Qté après',
        digits='Product Unit of Measure',
        default=0.0,
        help='Quantité en stock sur l\'emplacement après ce mouvement',
    )

    def write(self, vals):
        res = super().write(vals)
        if vals.get('state') == 'done' or vals.get('quantity'):
            done_lines = self.filtered(lambda l: l.state == 'done')
            if done_lines:
                done_lines._recompute_qty_for_lines()
        return res

    def _recompute_qty_for_lines(self):
        """
        Recalcule qty_before/after pour tous les emplacements impactés
        par les lignes de self. Un mouvement impacte deux emplacements :
        l'emplacement source (sortie) et l'emplacement destination (entrée).
        """
        affected = set()
        for line in self:
            affected.add((line.product_id.id, line.lot_id.id, line.location_id.id))
            affected.add((line.product_id.id, line.lot_id.id, line.location_dest_id.id))

        for product_id, lot_id, location_id in affected:
            self._recompute_location(product_id, lot_id, location_id)

    @api.model
    def _recompute_location(self, product_id, lot_id, location_id):
        """
        Pour un triplet (produit, lot, emplacement), recalcule qty_before/after
        sur toutes les move.line done qui touchent cet emplacement.

        Règles :
          - location_dest_id == location_id  → ENTREE  → +quantity
          - location_id      == location_id  → SORTIE  → -quantity
          - même emplacement source et dest  → neutre (delta = 0)

        Les lignes sont triées par date puis id pour garantir l'ordre chronologique.
        On écrit directement en SQL pour la performance.
        """
        lot_clause = 'AND lot_id = %s' if lot_id else 'AND lot_id IS NULL'
        lot_param = (lot_id,) if lot_id else ()

        # Récupérer toutes les lignes qui touchent cet emplacement (entrée OU sortie)
        sql = """
            SELECT id, location_id, location_dest_id, quantity, date
            FROM stock_move_line
            WHERE state = 'done'
              AND product_id = %s
              AND (location_id = %s OR location_dest_id = %s)
              {lot_clause}
            ORDER BY date ASC, id ASC
        """.format(lot_clause=lot_clause)

        params = (product_id, location_id, location_id) + lot_param
        self.env.cr.execute(sql, params)
        rows = self.env.cr.fetchall()

        running_qty = 0.0
        for (ml_id, loc_src, loc_dst, qty, date) in rows:
            qty_before = running_qty

            if loc_src == location_id and loc_dst == location_id:
                delta = 0.0          # transfert interne sur le même emplacement
            elif loc_dst == location_id:
                delta = qty          # ENTREE
            else:
                delta = -qty         # SORTIE

            running_qty += delta
            qty_after = running_qty

            self.env.cr.execute("""
                UPDATE stock_move_line
                SET x_qty_before = %s, x_qty_after = %s
                WHERE id = %s
            """, (qty_before, qty_after, ml_id))

    @api.model
    def recompute_all_history(self):
        """
        Recalcule qty_before/after sur TOUT l'historique existant.
        Appelé depuis le wizard de recalcul.
        """
        _logger.info('[StockMoveQty] Début recalcul historique complet')

        # Collecter toutes les combinaisons distinctes (produit, lot, emplacement)
        # en tenant compte des deux côtés du mouvement
        self.env.cr.execute("""
            SELECT DISTINCT product_id, COALESCE(lot_id, 0), location_id
            FROM stock_move_line WHERE state = 'done'
            UNION
            SELECT DISTINCT product_id, COALESCE(lot_id, 0), location_dest_id
            FROM stock_move_line WHERE state = 'done'
            ORDER BY 1, 2, 3
        """)
        combos = self.env.cr.fetchall()
        total = len(combos)
        _logger.info('[StockMoveQty] %d combinaisons à traiter', total)

        for i, (product_id, lot_id, location_id) in enumerate(combos):
            if i % 200 == 0:
                _logger.info('[StockMoveQty] Progression : %d/%d', i, total)
                self.env.cr.commit()

            real_lot_id = lot_id if lot_id != 0 else False
            self._recompute_location(product_id, real_lot_id, location_id)

        self.env.cr.commit()
        _logger.info('[StockMoveQty] Recalcul historique terminé')
        return True
