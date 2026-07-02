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
        for mo in self:
            if mo.sale_order_count:
                sale_orders = mo.procurement_group_id.mrp_production_ids.move_dest_ids.group_id.sale_id
                mo.x_studio_mtn_mrp_sale_order = sale_orders[:1]
