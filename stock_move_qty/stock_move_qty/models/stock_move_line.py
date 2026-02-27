# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = "stock.move"

    def _action_done(self, cancel_backorder=False):
        """
        Hook fiable à la validation (réception/livraison/transfert).
        On recalculera ensuite les Qté avant/après sur les move lines done.
        """
        res = super()._action_done(cancel_backorder=cancel_backorder)

        mls = self.mapped("move_line_ids").filtered(lambda l: l.state == "done")
        _logger.info("[StockMoveQty] _action_done moves=%s done_move_lines=%s", self.ids, len(mls))
        if mls:
            # petite trace (optionnelle)
            for l in mls[:10]:
                _logger.info(
                    "[StockMoveQty] DONE ML id=%s product=%s qty(UI)=%s src=%s dst=%s date=%s picking=%s",
                    l.id,
                    l.product_id.display_name,
                    l.quantity,
                    l.location_id.display_name,
                    l.location_dest_id.display_name,
                    l.date,
                    l.picking_id.name if l.picking_id else "",
                )
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
        help="Quantité en stock sur l'emplacement contexte avant ce mouvement",
    )
    x_qty_after = fields.Float(
        string="Qté après",
        digits="Product Unit of Measure",
        default=0.0,
        readonly=True,
        copy=False,
        help="Quantité en stock sur l'emplacement contexte après ce mouvement",
    )

    # -------------------------------------------------------------------------
    # Détection de la colonne SQL réellement stockée pour la quantité move line
    # (dans ta base, on a vu que c'est 'quantity')
    # -------------------------------------------------------------------------
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
        raise ValueError(
            "Impossible de trouver une colonne quantité stockée dans stock_move_line. "
            "Regarde les logs pour la liste des colonnes."
        )

    # -------------------------------------------------------------------------
    # Recalcul selon ta règle :
    # - mouvement d'entrée : Qté avant/après sur emplacement de destination
    # - mouvement de sortie : Qté avant/après sur emplacement source
    # - interne -> interne : on choisit destination
    # -------------------------------------------------------------------------
    def _recompute_qty_before_after_one_context(self):
        qty_col = self._get_done_qty_sql_column()

        # Groupes (product, lot, ctx_location) :
        # ctx_location = destination pour entrée / source pour sortie / destination pour interne->interne
        groups = {}
        for line in self:
            if line.state != "done":
                continue

            ctx_loc_id = self._ctx_location_id_for_line(line)
            key = (line.product_id.id, line.lot_id.id or False, ctx_loc_id)
            groups.setdefault(key, 0)
            groups[key] += 1

        _logger.info("[StockMoveQty] Recompute groups=%s", len(groups))

        for (product_id, lot_id, ctx_location_id) in groups.keys():
            self._recompute_group(product_id, lot_id, ctx_location_id, qty_col)

        self.invalidate_model(["x_qty_before", "x_qty_after"])

    @api.model
    def _ctx_location_id_for_line(self, line):
        """
        Détermine l'emplacement contexte pour UNE move line selon ta règle.
        On se base sur location.usage (internal/vendor/customer/production/inventory/transit...).
        """
        src_usage = line.location_id.usage
        dst_usage = line.location_dest_id.usage

        # Entrée : non-internal -> internal => contexte = destination
        if dst_usage == "internal" and src_usage != "internal":
            return line.location_dest_id.id

        # Sortie : internal -> non-internal => contexte = source
        if src_usage == "internal" and dst_usage != "internal":
            return line.location_id.id

        # Transfert interne : internal -> internal => contexte = destination
        if src_usage == "internal" and dst_usage == "internal":
            return line.location_dest_id.id

        # Fallback : on prend l'internal si présent, sinon destination
        if dst_usage == "internal":
            return line.location_dest_id.id
        if src_usage == "internal":
            return line.location_id.id
        return line.location_dest_id.id

    @api.model
    def _recompute_group(self, product_id, lot_id, ctx_location_id, qty_col):
        """
        Recalcule toutes les move lines done pour (product, lot) qui touchent ctx_location_id,
        puis met à jour SEULEMENT les lignes dont le contexte (entrée=dest / sortie=src) == ctx_location_id.
        Le calcul est cohérent avec le stock réel : on part du stock actuel (quant) et on remonte le temps.
        """
        lot_clause = "AND lot_id = %s" if lot_id else "AND lot_id IS NULL"
        lot_param = (lot_id,) if lot_id else ()

        sql = f"""
            SELECT id, location_id, location_dest_id, {qty_col}, date
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

        # Précharger usages des locations (évite browse+cache et skip involontaire)
        loc_ids = set()
        for (_ml_id, loc_src, loc_dst, _qty, _dt) in rows:
            loc_ids.add(loc_src)
            loc_ids.add(loc_dst)
        locs = self.env["stock.location"].browse(list(loc_ids)).read(["usage"])
        usage_by_id = {l["id"]: l["usage"] for l in locs}

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

        # Remonter le temps (desc) : after = running ; before = after - delta
        for (ml_id, loc_src, loc_dst, qty, dt) in rows:
            src_usage = usage_by_id.get(loc_src)
            dst_usage = usage_by_id.get(loc_dst)

            # Est-ce que CETTE ligne doit être mise à jour dans ce contexte ?
            # entrée -> destination ; sortie -> source ; interne->interne -> destination
            if dst_usage == "internal" and src_usage != "internal":
                include = (loc_dst == ctx_location_id)  # entrée
            elif src_usage == "internal" and dst_usage != "internal":
                include = (loc_src == ctx_location_id)  # sortie
            elif src_usage == "internal" and dst_usage == "internal":
                include = (loc_dst == ctx_location_id)  # interne->interne => destination
            else:
                # fallback : si une des deux est internal on la prend, sinon destination
                if dst_usage == "internal":
                    include = (loc_dst == ctx_location_id)
                elif src_usage == "internal":
                    include = (loc_src == ctx_location_id)
                else:
                    include = (loc_dst == ctx_location_id)

            # Delta appliqué sur la location contexte (pour remonter le temps)
            if loc_src == ctx_location_id and loc_dst == ctx_location_id:
                delta = 0.0
            elif loc_dst == ctx_location_id:
                delta = qty
            else:
                delta = -qty

            qty_after = running_qty
            qty_before = running_qty - delta
            running_qty = qty_before

            if not include:
                _logger.debug(
                    "[StockMoveQty] SKIP ML=%s dt=%s src=%s(%s) dst=%s(%s) qty=%s ctx=%s",
                    ml_id, dt, loc_src, src_usage, loc_dst, dst_usage, qty, ctx_location_id
                )
                continue

            _logger.debug(
                "[StockMoveQty] UPDATE ML=%s dt=%s qty=%s before=%s after=%s ctx=%s",
                ml_id, dt, qty, qty_before, qty_after, ctx_location_id
            )

            self.env.cr.execute(
                """
                UPDATE stock_move_line
                SET x_qty_before = %s, x_qty_after = %s
                WHERE id = %s
                """,
                (qty_before, qty_after, ml_id),
            )

    # -------------------------------------------------------------------------
    # Recalcul complet historique (optionnel)
    # -------------------------------------------------------------------------
    @api.model
    def recompute_all_history(self):
        _logger.info("[StockMoveQty] recompute_all_history START")
        qty_col = self._get_done_qty_sql_column()

        # Charger toutes les move lines done (attention: volumineux si très grand historique)
        self.env.cr.execute("SELECT id FROM stock_move_line WHERE state='done'")
        ids = [r[0] for r in self.env.cr.fetchall()]
        lines = self.browse(ids)

        groups = {}
        for l in lines:
            ctx_loc_id = self._ctx_location_id_for_line(l)
            key = (l.product_id.id, l.lot_id.id or False, ctx_loc_id)
            groups.setdefault(key, 0)
            groups[key] += 1

        _logger.info("[StockMoveQty] recompute_all_history groups=%s", len(groups))

        for i, (product_id, lot_id, ctx_location_id) in enumerate(groups.keys()):
            if i % 200 == 0:
                _logger.info("[StockMoveQty] progress %s/%s", i, len(groups))
                self.env.cr.commit()
            self._recompute_group(product_id, lot_id, ctx_location_id, qty_col)

        self.env.cr.commit()
        self.invalidate_model(["x_qty_before", "x_qty_after"])
        _logger.info("[StockMoveQty] recompute_all_history DONE")
        return True
