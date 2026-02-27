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
            mls._recompute_qty_before_after_one_context()

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
    # Détection colonne quantité réellement stockée (ta DB = quantity)
    # ----------------------------
    @api.model
    def _get_done_qty_sql_column(self):
        candidates = ["qty_done", "quantity", "product_qty", "product_uom_qty", "qty"]

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

        _logger.error("[StockMoveQty] Aucune colonne quantité trouvée. Colonnes dispo: %s", sorted(cols))
        raise ValueError("Impossible de trouver une colonne quantité dans stock_move_line (voir logs).")

    # ----------------------------
    # Règle métier demandée : entrée=destination / sortie=source
    # ----------------------------
    def _get_context_location_for_line(self):
        """
        Retourne l'emplacement 'contexte' sur lequel on veut calculer Qté avant/après :
          - entrée : destination
          - sortie : source
          - interne->interne : destination (choix)
        On se base sur la 'usage' des locations (internal/vendor/customer/inventory/production/transit...).
        """
        self.ensure_one()
        src_usage = self.location_id.usage
        dst_usage = self.location_dest_id.usage

        # Entrée en stock : source non-internal -> dest internal
        if dst_usage == "internal" and src_usage != "internal":
            return self.location_dest_id

        # Sortie de stock : source internal -> dest non-internal
        if src_usage == "internal" and dst_usage != "internal":
            return self.location_id

        # Transfert interne : internal -> internal (on choisit destination)
        if src_usage == "internal" and dst_usage == "internal":
            return self.location_dest_id

        # Cas atypiques (inventory adjustments, production, transit...) :
        # on privilégie l'emplacement internal s'il y en a un, sinon destination
        if dst_usage == "internal":
            return self.location_dest_id
        if src_usage == "internal":
            return self.location_id
        return self.location_dest_id

    # ----------------------------
    # Recalcul principal (1 seul contexte par move line)
    # ----------------------------
    def _recompute_qty_before_after_one_context(self):
        """
        Recalcule x_qty_before/x_qty_after pour chaque move line done
        selon la règle entrée=dest / sortie=source.
        Le calcul est cohérent avec le stock réel : on part du stock actuel (stock.quant)
        et on remonte l'historique (ORDER BY date DESC).
        """
        qty_col = self._get_done_qty_sql_column()

        # On traite par groupe (product, lot, context_location) pour recalculer un historique cohérent
        groups = {}
        for line in self:
            if line.state != "done":
                continue
            ctx_loc = line._get_context_location_for_line()
            key = (line.product_id.id, line.lot_id.id or False, ctx_loc.id)
            groups.setdefault(key, []).append(line.id)

        _logger.info("[StockMoveQty] Recompute groups=%s", len(groups))

        for (product_id, lot_id, ctx_location_id), _line_ids in groups.items():
            self._recompute_group(product_id, lot_id, ctx_location_id, qty_col)

        self.invalidate_model(["x_qty_before", "x_qty_after"])

    @api.model
    def _recompute_group(self, product_id, lot_id, ctx_location_id, qty_col):
        """
        Recalcule toutes les move lines done du produit/lot qui concernent le ctx_location_id,
        MAIS en ne gardant que les lignes dont le contexte (entrée=dest / sortie=src) est CE ctx_location_id.
        Ainsi : aucune écrasement et résultat conforme à ton besoin.
        """
        lot_clause = "AND lot_id = %s" if lot_id else "AND lot_id IS NULL"
        lot_param = (lot_id,) if lot_id else ()

        # On récupère toutes les lignes "touchant" cette location (src ou dst)
        # puis on filtrera en Python celles dont le contexte = ctx_location_id.
        sql = f"""
            SELECT id, location_id, location_dest_id, {qty_col}, date, product_id, lot_id
            FROM stock_move_line
            WHERE state = 'done'
              AND product_id = %s
              AND (location_id = %s OR location_dest_id = %s)
              {lot_clause}
            ORDER BY date DESC, id DESC
        """
        params = (product_id, ctx_location_id, ctx_location_id) + lot_param
        self.env.cr.execute(sql, params)
        rows = self.env.cr.fetchall()

        _logger.info(
            "[StockMoveQty] Group product=%s lot=%s ctx_loc=%s rows=%s qty_col=%s",
            product_id, lot_id or "NULL", ctx_location_id, len(rows), qty_col
        )
        if not rows:
            return

        # Stock actuel sur la location contexte (après tous mouvements)
        Quant = self.env["stock.quant"].sudo()
        domain = [("product_id", "=", product_id), ("location_id", "=", ctx_location_id)]
        domain.append(("lot_id", "=", lot_id) if lot_id else ("lot_id", "=", False))
        current_qty = sum(Quant.search(domain).mapped("quantity")) or 0.0
        running_qty = current_qty

        _logger.info(
            "[StockMoveQty] ctx_loc=%s product=%s lot=%s stock_actuel=%s",
            ctx_location_id, product_id, lot_id or "NULL", current_qty
        )

        # Remontée dans le temps : after = running, before = after - delta
        # Mais on UPDATE uniquement les lignes dont le "contexte" = ctx_location_id
        for (ml_id, loc_src, loc_dst, qty, dt, _p, _l) in rows:
            # delta sur la location ctx
            if loc_src == ctx_location_id and loc_dst == ctx_location_id:
                delta = 0.0
            elif loc_dst == ctx_location_id:
                delta = qty
            else:
                delta = -qty

            qty_after = running_qty
            qty_before = running_qty - delta
            running_qty = qty_before

            # Filtre : est-ce que cette move line doit être affichée avec ctx = destination ou source ?
            ml = self.browse(ml_id)
            ctx_loc = ml._get_context_location_for_line()
            if ctx_loc.id != ctx_location_id:
                # On ne met pas à jour cette ligne (sinon écrasement et incohérence)
                continue

            _logger.debug(
                "[StockMoveQty] UPDATE ML=%s dt=%s ctx_loc=%s src=%s dst=%s qty=%s before=%s after=%s",
                ml_id, dt, ctx_location_id, loc_src, loc_dst, qty, qty_before, qty_after
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
        """
        Recalcule tout l'historique avec la règle :
        - entrée -> destination
        - sortie -> source
        - interne -> destination
        """
        _logger.info("[StockMoveQty] recompute_all_history START")

        # On prend toutes les move lines done et on crée les groupes (product, lot, ctx_location)
        self.env.cr.execute("""
            SELECT id
            FROM stock_move_line
            WHERE state = 'done'
        """)
        ids = [r[0] for r in self.env.cr.fetchall()]
        lines = self.browse(ids)

        qty_col = self._get_done_qty_sql_column()

        groups = {}
        for l in lines:
            ctx_loc = l._get_context_location_for_line()
            key = (l.product_id.id, l.lot_id.id or False, ctx_loc.id)
            groups.setdefault(key, 0)
            groups[key] += 1

        _logger.info("[StockMoveQty] recompute_all_history groups=%s", len(groups))

        for i, (key, _count) in enumerate(groups.items()):
            if i % 200 == 0:
                _logger.info("[StockMoveQty] progress %s/%s", i, len(groups))
                self.env.cr.commit()
            product_id, lot_id, ctx_location_id = key
            self._recompute_group(product_id, lot_id, ctx_location_id, qty_col)

        self.env.cr.commit()
        self.invalidate_model(["x_qty_before", "x_qty_after"])
        _logger.info("[StockMoveQty] recompute_all_history DONE")
        return True
