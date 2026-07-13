# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Business rule migrated from Odoo Studio automation
"MTN : SO sur MO pour récupérer projet" (staging DB, audited 2026-07-02).
See STUDIO_AUDIT.md at the repo root for the full inventory.
"""
from odoo import models


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def create(self, vals_list):
        productions = super().create(vals_list)
        productions.with_context(skip_studio_sync=True)._sync_studio_sale_order()
        return productions

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("skip_studio_sync"):
            self.with_context(skip_studio_sync=True)._sync_studio_sale_order()
        return res

    def _sync_studio_sale_order(self):
        StockMove = self.env["stock.move"]
        for mo in self:
            if not mo.sale_order_count:
                continue

            sale_orders = self.env["sale.order"]
            if "sale_line_id" in mo._fields:
                sale_orders = mo.sale_line_id.order_id

            if not sale_orders:
                # procurement_group_id (v17/v18) devient production_group_id (v19),
                # avec mrp_production_ids renommé production_ids.
                if "production_group_id" in mo._fields:
                    siblings = mo.production_group_id.production_ids
                elif "procurement_group_id" in mo._fields:
                    siblings = mo.procurement_group_id.mrp_production_ids
                else:
                    siblings = mo
                moves = siblings.move_dest_ids
                # stock.move.group_id existait jusqu'en v18, supprimé en v19
                # (remplacé par un lien direct move -> vente via sale_line_id/picking_id).
                if "group_id" in StockMove._fields and moves.group_id:
                    sale_orders = moves.group_id.sale_id
                elif "sale_line_id" in StockMove._fields:
                    sale_orders = moves.sale_line_id.order_id
                else:
                    sale_orders = moves.picking_id.sale_id

            mo.x_studio_mtn_mrp_sale_order = sale_orders[:1]
