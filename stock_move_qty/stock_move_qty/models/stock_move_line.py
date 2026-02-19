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
        help='Quantité en stock avant ce mouvement',
    )
    x_qty_after = fields.Float(
        string='Qté après',
        digits='Product Unit of Measure',
        default=0.0,
        help='Quantité en stock après ce mouvement',
    )

    def _compute_qty_before_after(self):
        """
        Calcule x_qty_before et x_qty_after pour les lignes de mouvement.
        Logique :
          - Pour chaque combinaison (produit, lot, emplacement destination),
            on cumule les qty_done des move.line validées dans l'ordre chronologique.
          - qty_before = cumul AVANT la ligne courante
          - qty_after  = cumul APRES  la ligne courante
        """
        # On ne traite que les lignes "done" (state = done sur le move parent)
        lines = self.filtered(lambda l: l.state == 'done')
        if not lines:
            return

        # Regrouper par (product_id, lot_id, location_dest_id)
        # pour recalculer le stock cumulé par emplacement
        groups = {}
        for line in lines:
            key = (line.product_id.id, line.lot_id.id, line.location_dest_id.id)
            groups.setdefault(key, []).append(line)

        for key, group_lines in groups.items():
            # Récupérer TOUT l'historique pour cette clé (pas seulement self)
            product_id, lot_id, location_dest_id = key
            domain = [
                ('product_id', '=', product_id),
                ('location_dest_id', '=', location_dest_id),
                ('state', '=', 'done'),
            ]
            if lot_id:
                domain.append(('lot_id', '=', lot_id))

            all_lines = self.search(domain, order='date asc, id asc')

            # Recalculer le cumul complet
            running_qty = 0.0
            qty_map = {}
            for ml in all_lines:
                qty_before = running_qty
                # Mouvements entrants : on ajoute, sortants : on soustrait
                if ml.location_dest_id.id == location_dest_id:
                    running_qty += ml.quantity
                else:
                    running_qty -= ml.quantity
                qty_map[ml.id] = (qty_before, running_qty)

            # Écrire uniquement sur les lignes de self qui sont dans ce groupe
            ids_in_group = {l.id for l in group_lines}
            lines_to_write = self.browse([mid for mid in qty_map if mid in ids_in_group])
            for ml in lines_to_write:
                before, after = qty_map[ml.id]
                ml.write({
                    'x_qty_before': before,
                    'x_qty_after': after,
                })

    def write(self, vals):
        res = super().write(vals)
        # Recalcule automatiquement quand le mouvement passe à done
        if vals.get('state') == 'done' or vals.get('quantity'):
            done_lines = self.filtered(lambda l: l.state == 'done')
            if done_lines:
                done_lines._compute_qty_before_after()
        return res

    @api.model
    def recompute_all_history(self):
        """
        Recalcule qty_before/after sur TOUT l'historique existant.
        Appelé depuis le wizard ou manuellement.
        Traitement par batch pour éviter les timeouts.
        """
        _logger.info('[StockMoveQty] Début recalcul historique complet')

        # Récupérer toutes les combinaisons distinctes (produit, lot, emplacement)
        self.env.cr.execute("""
            SELECT DISTINCT product_id, lot_id, location_dest_id
            FROM stock_move_line
            WHERE state = 'done'
            ORDER BY product_id, lot_id, location_dest_id
        """)
        combos = self.env.cr.fetchall()
        total = len(combos)
        _logger.info('[StockMoveQty] %d combinaisons à traiter', total)

        for i, (product_id, lot_id, location_dest_id) in enumerate(combos):
            if i % 100 == 0:
                _logger.info('[StockMoveQty] Progression : %d/%d', i, total)
                self.env.cr.commit()  # commit partiel pour éviter les locks

            domain = [
                ('product_id', '=', product_id),
                ('location_dest_id', '=', location_dest_id),
                ('state', '=', 'done'),
            ]
            if lot_id:
                domain.append(('lot_id', '=', lot_id))

            all_lines = self.search(domain, order='date asc, id asc')

            running_qty = 0.0
            for ml in all_lines:
                qty_before = running_qty
                running_qty += ml.quantity
                # Écriture directe SQL pour la performance sur gros volumes
                self.env.cr.execute("""
                    UPDATE stock_move_line
                    SET x_qty_before = %s, x_qty_after = %s
                    WHERE id = %s
                """, (qty_before, running_qty, ml.id))

        self.env.cr.commit()
        _logger.info('[StockMoveQty] Recalcul historique terminé')
        return True
