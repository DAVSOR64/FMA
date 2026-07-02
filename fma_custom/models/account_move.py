# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Business rule migrated from Odoo Studio automation "Facture fournisseur"
(staging DB, audited 2026-07-02). Complements (does not duplicate) the
inv_activite logic already in custom_invoice/models/account_move.py, which
only fires for customer invoices linked to a sale.order via invoice_origin;
this one fires for supplier bills linked to a purchase.order instead.
See STUDIO_AUDIT.md at the repo root for the full inventory.
"""
from odoo import models

WAREHOUSE_ACTIVITE_MAP = {
    "REGRIPPIERE": "ALU",
    "REMAUDIERE": "ACIER",
}


class AccountMove(models.Model):
    _inherit = "account.move"

    def create(self, vals_list):
        moves = super().create(vals_list)
        moves.filtered(
            lambda m: m.move_type == "in_invoice"
        ).with_context(skip_studio_sync=True)._sync_studio_activite()
        return moves

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("skip_studio_sync"):
            self.filtered(
                lambda m: m.move_type == "in_invoice"
            ).with_context(skip_studio_sync=True)._sync_studio_activite()
        return res

    def _sync_studio_activite(self):
        for move in self:
            if not move.invoice_origin:
                continue
            po = self.env["purchase.order"].search([("name", "=", move.invoice_origin)], limit=1)
            if not (po and po.picking_type_id and po.picking_type_id.warehouse_id):
                continue
            warehouse_name = po.picking_type_id.warehouse_id.name
            for keyword, activite in WAREHOUSE_ACTIVITE_MAP.items():
                if keyword in warehouse_name:
                    move.inv_activite = activite
                    break
