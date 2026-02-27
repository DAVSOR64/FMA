# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = "stock.move"

    def _action_done(self, cancel_backorder=False):
        res = super()._action_done(cancel_backorder=cancel_backorder)

        mls = self.mapped("move_line_ids").filtered(lambda l: l.state == "done")
        _logger.info("[StockMoveQty] _action_done moves=%s done_move_lines=%s", self.ids, len(mls))

        if mls:
            for l in mls[:10]:
                _logger.info(
                    "[StockMoveQty] DONE ML id=%s product=%s quantity(UI)=%s src=%s dst=%s date=%s picking=%s",
                    l.id,
                    l.product_id.display_name,
                    l.quantity,  # champ UI (peut être computed)
                    l.location_id.display_name,
                    l.location_dest_id.display_name,
                    l.date,
                    l.picking_id.name if l.picking_id else "",
                )
            mls._recompute_qty_for_lines()

        return res


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    x_qty_before = fields.Float(
        string="Qté avant",
        digits="Product Unit of Measure",
        default=0.0,
        readonly=True,
        copy=False,
    )
    x_qty_after = fields.Float(
        string="Qté après",
        digits="Product Unit of Measure",
        default=0.0,
        readonly=True,
        copy=False,
    )

    # ----------------------------
    # Détection colonne quantité réellement stockée
    # ----------------------------
    @api.model
    def _get_done_qty_sql_column(self):
        """
        Détermine la colonne SQL qui contient la quantité faite sur stock_move_line
        en inspectant la base (information_schema).
        On teste une liste de candidats connus et on garde le premier présent.
        """
        candidates = [
            "qty_done",
            "quantity",
            "product_qty",
            "product_uom_qty",
            "qty",  # fallback rare
        ]

        self.env.cr.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'stock_move_line'
        """)
        cols = {r[0] for r in self.env.cr.fetchall()}

        for c in candidates:
            if c in cols:
                _logger.info("[StockMoveQty] Colonne quantité détectée en DB: %s", c)
                return c

        # Si aucune trouvée, on log les colonnes existantes pour diagnostic
        _logger.error("[StockMoveQty] Aucune colonne quantité trouvée. Colonnes dispo: %s", sorted(cols))
        raise ValueError(
            "Impossible de trouver une colonne quantité dans stock_move_line. "
            "Regarde les logs pour la liste des colonnes disponibles."
        )

    def write(self, vals):
        res = super().write(vals)

        trigger = (
            vals.get("state") == "done"
            or "location_id" in vals
            or "location_dest_id" in vals
            or "lot_id" in vals
            or "product_id" in vals
            # quantité UI modifiée (même si computed, ça peut déclencher des écritures indirectes)
            or "quantity" in vals
        )
        if trigger:
            done_lines = self.filtered(lambda l: l.state == "done")
            if done_lines:
                _logger.debug("[StockMoveQty] write trigger recompute done_lines=%s", done_lines.ids)
                done_lines._recompute_qty_for_lines()

        return res

    def _recompute_qty_for_lines(self):
        affected = set()
        for line in self:
            affected.add((line.product_id.id, line.lot_id.id, line.location_id.id))
            affected.add((line.product_id.id, line.lot_id.id, line.location_dest_id.id))

        _logger.info("[StockMoveQty] _recompute_qty_for_lines affected=%s", len(affected))

        for product_id, lot_id, location_id in affected:
            self._recompute_location(product_id, lot_id, location_id)

        self.invalidate_model(["x_qty_before", "x_qty_after"])

    @api.model
    def _recompute_location(self, product_id, lot_id, location_id):
        lot_clause = "AND lot_id = %s" if lot_id else "AND lot_id IS NULL"
        lot_param = (lot_id,) if lot_id else ()

        qty_col = self._get_done_qty_sql_column()

        sql = f"""
            SELECT id, location_id, location_dest_id, {qty_col}, date
            FROM stock_move_line
            WHERE state = 'done'
              AND product_id = %s
              AND (location_id = %s OR location_dest_id = %s)
              {lot_clause}
            ORDER BY date ASC, id ASC
        """
        params = (product_id, location_id, location_id) + lot_param
        self.env.cr.execute(sql, params)
        rows = self.env.cr.fetchall()

        _logger.info(
            "[StockMoveQty] _recompute_location product=%s lot=%s loc=%s -> rows=%s (qty_col=%s)",
            product_id, lot_id or "NULL", location_id, len(rows), qty_col
        )

        running_qty = 0.0
        for (ml_id, loc_src, loc_dst, qty, dt) in rows:
            qty_before = running_qty

            if loc_src == location_id and loc_dst == location_id:
                delta = 0.0
            elif loc_dst == location_id:
                delta = qty
            else:
                delta = -qty

            running_qty += delta
            qty_after = running_qty

            _logger.debug(
                "[StockMoveQty] ML=%s dt=%s src=%s dst=%s qty=%s before=%s delta=%s after=%s loc_ctx=%s",
                ml_id, dt, loc_src, loc_dst, qty, qty_before, delta, qty_after, location_id
            )

            self.env.cr.execute(
                """
                UPDATE stock_move_line
                SET x_qty_before = %s, x_qty_after = %s
                WHERE id = %s
                """,
                (qty_before, qty_after, ml_id),
            )

    @api.model
    def recompute_all_history(self):
        _logger.info("[StockMoveQty] Recompute all history START")

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
        _logger.info("[StockMoveQty] Combos=%s", total)

        for i, (product_id, lot_id, location_id) in enumerate(combos):
            if i % 200 == 0:
                _logger.info("[StockMoveQty] Progress %s/%s", i, total)
                self.env.cr.commit()

            real_lot_id = lot_id if lot_id != 0 else False
            self._recompute_location(product_id, real_lot_id, location_id)

        self.env.cr.commit()
        self.invalidate_model(["x_qty_before", "x_qty_after"])
        _logger.info("[StockMoveQty] Recompute all history DONE")
        return True
