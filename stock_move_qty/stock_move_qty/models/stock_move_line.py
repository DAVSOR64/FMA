# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = "stock.move"

    def _action_done(self, cancel_backorder=False):
        """
        Hook fiable : appelé lors de la validation (réception/livraison/OF etc.)
        On laisse Odoo terminer, puis on recalcule qty_before/after pour les move lines done.
        """
        res = super()._action_done(cancel_backorder=cancel_backorder)

        # Après _action_done, les move lines sont normalement en done
        mls = self.mapped("move_line_ids").filtered(lambda l: l.state == "done")
        if mls:
            _logger.info(
                "[StockMoveQty] _action_done: %s move lines done à recalculer (moves=%s)",
                len(mls),
                ",".join(map(str, self.ids)),
            )
            # petite trace de quelques lignes
            for l in mls[:10]:
                _logger.info(
                    "[StockMoveQty] DONE ML id=%s product=%s qty_done=%s src=%s dst=%s date=%s picking=%s",
                    l.id,
                    l.product_id.display_name,
                    l.qty_done,
                    l.location_id.display_name,
                    l.location_dest_id.display_name,
                    l.date,
                    l.picking_id.name if l.picking_id else "",
                )

            mls._recompute_qty_for_lines()
        else:
            _logger.info(
                "[StockMoveQty] _action_done: aucune move line done trouvée (moves=%s). "
                "Vérifie si move_line_ids est rempli ou si state est bien done.",
                ",".join(map(str, self.ids)),
            )

        return res


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    x_qty_before = fields.Float(
        string="Qté avant",
        digits="Product Unit of Measure",
        default=0.0,
        readonly=True,
        copy=False,
        help="Quantité en stock sur l'emplacement (contexte emplacement) avant ce mouvement",
    )
    x_qty_after = fields.Float(
        string="Qté après",
        digits="Product Unit of Measure",
        default=0.0,
        readonly=True,
        copy=False,
        help="Quantité en stock sur l'emplacement (contexte emplacement) après ce mouvement",
    )

    def write(self, vals):
        """
        On garde le write (utile si modifications manuelles), mais le hook principal
        est désormais _action_done sur stock.move.
        """
        res = super().write(vals)

        trigger = (
            vals.get("state") == "done"
            or "qty_done" in vals
            or "location_id" in vals
            or "location_dest_id" in vals
            or "lot_id" in vals
            or "product_id" in vals
        )
        if trigger:
            done_lines = self.filtered(lambda l: l.state == "done")
            if done_lines:
                _logger.debug(
                    "[StockMoveQty] write trigger: recompute sur %s lignes done (ids=%s)",
                    len(done_lines),
                    done_lines.ids,
                )
                done_lines._recompute_qty_for_lines()

        return res

    def _recompute_qty_for_lines(self):
        """
        Recalcule x_qty_before/x_qty_after pour tous les emplacements impactés
        par les lignes de self.
        """
        affected = set()
        for line in self:
            affected.add((line.product_id.id, line.lot_id.id, line.location_id.id))
            affected.add((line.product_id.id, line.lot_id.id, line.location_dest_id.id))

        _logger.info(
            "[StockMoveQty] _recompute_qty_for_lines: %s combinaisons (product,lot,location) à recalculer",
            len(affected),
        )

        for product_id, lot_id, location_id in affected:
            self._recompute_location(product_id, lot_id, location_id)

        # Invalide cache après UPDATE SQL
        self.invalidate_model(["x_qty_before", "x_qty_after"])

    @api.model
    def _recompute_location(self, product_id, lot_id, location_id):
        """
        Pour un triplet (produit, lot, emplacement), recalcule x_qty_before/x_qty_after
        sur toutes les move.line done qui touchent cet emplacement.
        Odoo 17 : qty_done.
        """
        lot_clause = "AND lot_id = %s" if lot_id else "AND lot_id IS NULL"
        lot_param = (lot_id,) if lot_id else ()

        sql = """
            SELECT id, location_id, location_dest_id, qty_done, date
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

        # TRACE SQL
        _logger.info(
            "[StockMoveQty] _recompute_location: product_id=%s lot_id=%s location_id=%s -> %s lignes SQL",
            product_id,
            lot_id or "NULL",
            location_id,
            len(rows),
        )

        if not rows:
            # C'est une info super importante : si 0 lignes, c'est ton WHERE qui ne match pas
            # (state pas done, product_id différent, location_id pas celui attendu, etc.)
            return

        running_qty = 0.0
        for (ml_id, loc_src, loc_dst, qty_done, dt) in rows:
            qty_before = running_qty

            if loc_src == location_id and loc_dst == location_id:
                delta = 0.0
            elif loc_dst == location_id:
                delta = qty_done
            else:
                delta = -qty_done

            running_qty += delta
            qty_after = running_qty

            # TRACE DETAILLEE (tu peux passer en debug si trop bavard)
            _logger.debug(
                "[StockMoveQty] ML=%s dt=%s src=%s dst=%s qty_done=%s | before=%s delta=%s after=%s (loc_ctx=%s)",
                ml_id, dt, loc_src, loc_dst, qty_done,
                qty_before, delta, qty_after, location_id
            )

            self.env.cr.execute(
                """
                UPDATE stock_move_line
                SET x_qty_before = %s,
                    x_qty_after = %s
                WHERE id = %s
                """,
                (qty_before, qty_after, ml_id),
            )

    @api.model
    def recompute_all_history(self):
        _logger.info("[StockMoveQty] Début recalcul historique complet")

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
        _logger.info("[StockMoveQty] %d combinaisons à traiter", total)

        for i, (product_id, lot_id, location_id) in enumerate(combos):
            if i % 200 == 0:
                _logger.info("[StockMoveQty] Progression : %d/%d", i, total)
                self.env.cr.commit()

            real_lot_id = lot_id if lot_id != 0 else False
            self._recompute_location(product_id, real_lot_id, location_id)

        self.env.cr.commit()
        self.invalidate_model(["x_qty_before", "x_qty_after"])
        _logger.info("[StockMoveQty] Recalcul historique terminé")
        return True
