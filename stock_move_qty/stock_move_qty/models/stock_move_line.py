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
                    "[StockMoveQty] DONE ML id=%s product=%s qty(UI)=%s src=%s(%s) dst=%s(%s) date=%s picking=%s",
                    l.id,
                    l.product_id.display_name,
                    l.quantity,
                    l.location_id.display_name, l.location_id.usage,
                    l.location_dest_id.display_name, l.location_dest_id.usage,
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
    )
    x_qty_after = fields.Float(
        string="Qté après",
        digits="Product Unit of Measure",
        default=0.0,
        readonly=True,
        copy=False,
    )

    # -------------------------------------------------------------------------
    # Règle métier demandée :
    # - mouvement d'entrée : Qté avant/après sur emplacement de destination
    # - mouvement de sortie : Qté avant/après sur emplacement source
    # - interne -> interne : destination
    #
    # Et SI l'emplacement contexte est "view", on raisonne sur le périmètre child_of.
    # -------------------------------------------------------------------------

    @api.model
    def _ctx_location_for_line(self, line):
        """Retourne la location 'contexte' (record) selon ta règle."""
        src = line.location_id
        dst = line.location_dest_id

        src_usage = src.usage
        dst_usage = dst.usage

        # Entrée (supplier/customer/...) -> internal : contexte = destination
        if dst_usage == "internal" and src_usage != "internal":
            return dst

        # Sortie internal -> autre : contexte = source
        if src_usage == "internal" and dst_usage != "internal":
            return src

        # Transfert internal -> internal : contexte = destination
        if src_usage == "internal" and dst_usage == "internal":
            return dst

        # Fallback : on prend l'internal s'il existe, sinon destination
        if dst_usage == "internal":
            return dst
        if src_usage == "internal":
            return src
        return dst

    @api.model
    def _ctx_domain_for_location(self, ctx_location):
        """
        Domaine "périmètre" pour une location contexte :
        - si usage=view : child_of (location + enfants)
        - sinon : location exacte
        """
        if ctx_location.usage == "view":
            return ("child_of", ctx_location.id)
        return ("=", ctx_location.id)

    def _recompute_qty_before_after_one_context(self):
        """
        Recalcule x_qty_before/x_qty_after pour les lignes done de self,
        en groupant par (product, lot, ctx_location) et en recalculant l'historique
        depuis le stock actuel (stock.quant) sur le périmètre ctx (location ou child_of).
        """
        groups = {}
        for line in self.filtered(lambda l: l.state == "done"):
            ctx_loc = self._ctx_location_for_line(line)
            key = (line.product_id.id, line.lot_id.id or False, ctx_loc.id)
            groups.setdefault(key, ctx_loc)

        _logger.info("[StockMoveQty] Recompute groups=%s", len(groups))

        for (product_id, lot_id, ctx_loc_id), ctx_loc in groups.items():
            self._recompute_group(product_id, lot_id, ctx_loc)

        self.invalidate_model(["x_qty_before", "x_qty_after"])

    @api.model
    def _recompute_group(self, product_id, lot_id, ctx_loc):
        """
        Recalcule l'historique (avant/après) pour un triplet (product, lot, ctx_location).
        On récupère toutes les move lines done qui "touchent" le périmètre ctx (source OU destination),
        puis on remonte le temps depuis le stock actuel (stock.quant).

        IMPORTANT : on ne met à jour que les lignes dont le contexte (entrée=dest / sortie=src) retombe sur ctx_loc.
        Et si ctx_loc est view, on accepte que le contexte retombe sur un enfant internal (child_of).
        """
        ctx_op, ctx_val = self._ctx_domain_for_location(ctx_loc)

        domain = [
            ("state", "=", "done"),
            ("product_id", "=", product_id),
            "|",
            ("location_id", ctx_op, ctx_val),
            ("location_dest_id", ctx_op, ctx_val),
        ]
        if lot_id:
            domain.append(("lot_id", "=", lot_id))
        else:
            domain.append(("lot_id", "=", False))

        # Trier du plus récent au plus ancien (remontée du temps)
        lines = self.search(domain, order="date desc, id desc")

        _logger.info(
            "[StockMoveQty] Group product=%s lot=%s ctx=%s(%s) lines=%s",
            product_id, lot_id or "NULL", ctx_loc.display_name, ctx_loc.usage, len(lines)
        )
        if not lines:
            return

        # Stock actuel sur le périmètre ctx (quant sur location ou child_of)
        Quant = self.env["stock.quant"].sudo()
        q_domain = [("product_id", "=", product_id), ("location_id", ctx_op, ctx_val)]
        if lot_id:
            q_domain.append(("lot_id", "=", lot_id))
        else:
            q_domain.append(("lot_id", "=", False))
        current_qty = sum(Quant.search(q_domain).mapped("quantity")) or 0.0
        running_qty = current_qty

        _logger.info(
            "[StockMoveQty] ctx=%s stock_actuel=%s (quant domain=%s %s)",
            ctx_loc.display_name, current_qty, ctx_op, ctx_val
        )

        # Pour décider "include" quand ctx_loc est view :
        # on considère qu'une ligne est "dans le contexte" si la location choisie (src/dst selon règle)
        # est soit exactement ctx_loc, soit dans child_of(ctx_loc).
        def _is_in_ctx(loc):
            if ctx_loc.usage == "view":
                return loc.id in self.env["stock.location"].search([("id", "child_of", ctx_loc.id)]).ids
            return loc.id == ctx_loc.id

        # ⚠️ optimisation simple : si ctx_loc.view, précharger l'ensemble child_of une fois
        ctx_child_ids = None
        if ctx_loc.usage == "view":
            ctx_child_ids = set(self.env["stock.location"].search([("id", "child_of", ctx_loc.id)]).ids)

            def _is_in_ctx(loc):
                return loc.id in ctx_child_ids

        for ml in lines:
            # delta sur le périmètre ctx :
            # - si destination dans ctx => entrée (+)
            # - si source dans ctx => sortie (-)
            # - si les deux dans ctx => delta 0 (transfert interne dans même périmètre)
            src_in = _is_in_ctx(ml.location_id)
            dst_in = _is_in_ctx(ml.location_dest_id)

            if src_in and dst_in:
                delta = 0.0
            elif dst_in:
                delta = ml.quantity
            else:
                delta = -ml.quantity

            qty_after = running_qty
            qty_before = running_qty - delta
            running_qty = qty_before

            # Décider si cette move line doit recevoir x_qty_before/after selon ta règle
            ctx_for_line = self._ctx_location_for_line(ml)
            include = _is_in_ctx(ctx_for_line)

            if not include:
                _logger.debug(
                    "[StockMoveQty] SKIP ML=%s dt=%s qty=%s src=%s(%s) dst=%s(%s) ctx_for_line=%s ctx=%s",
                    ml.id, ml.date, ml.quantity,
                    ml.location_id.display_name, ml.location_id.usage,
                    ml.location_dest_id.display_name, ml.location_dest_id.usage,
                    ctx_for_line.display_name, ctx_loc.display_name
                )
                continue

            _logger.debug(
                "[StockMoveQty] UPDATE ML=%s dt=%s qty=%s before=%s after=%s ctx=%s",
                ml.id, ml.date, ml.quantity, qty_before, qty_after, ctx_loc.display_name
            )

            ml.sudo().write({"x_qty_before": qty_before, "x_qty_after": qty_after})

    @api.model
    def recompute_all_history(self):
        """
        Recalcul complet historique (à lancer via action serveur / shell).
        """
        _logger.info("[StockMoveQty] recompute_all_history START")
        done_lines = self.search([("state", "=", "done")])

        # construire les groupes (product, lot, ctx_location)
        groups = {}
        for ml in done_lines:
            ctx_loc = self._ctx_location_for_line(ml)
            key = (ml.product_id.id, ml.lot_id.id or False, ctx_loc.id)
            groups.setdefault(key, ctx_loc)

        _logger.info("[StockMoveQty] recompute_all_history groups=%s", len(groups))

        for i, ((product_id, lot_id, _ctx_id), ctx_loc) in enumerate(groups.items()):
            if i % 200 == 0:
                _logger.info("[StockMoveQty] progress %s/%s", i, len(groups))
                self.env.cr.commit()
            self._recompute_group(product_id, lot_id, ctx_loc)

        self.env.cr.commit()
        _logger.info("[StockMoveQty] recompute_all_history DONE")
        return True
