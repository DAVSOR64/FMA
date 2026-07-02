# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Business rule migrated from the Odoo Studio server action
"Création Facture Fournisseur en masse" (staging DB, audited 2026-07-02).
See STUDIO_AUDIT.md at the repo root for the full inventory.
"""
from odoo import _, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def action_create_supplier_invoices(self):
        purchase_orders = self.move_ids.purchase_line_id.order_id
        purchase_orders = purchase_orders.filtered(lambda po: po.invoice_status == "to invoice")
        if not purchase_orders:
            raise UserError(_("Aucune commande à facturer parmi les réceptions sélectionnées."))
        return purchase_orders.action_create_invoice()
