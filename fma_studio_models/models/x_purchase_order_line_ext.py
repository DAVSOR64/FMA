# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Real model replacing the Odoo Studio "manual" model
x_purchase_order_line_35a7b, plus the one2many field Studio added on
purchase.order to expose it (staging DB, audited 2026-07-02).
See STUDIO_AUDIT.md at the repo root -- this model only has a
name/sequence skeleton, no other business field was ever added to it.
"""
from odoo import fields, models


class XPurchaseOrderLine35a7b(models.Model):
    _name = "x_purchase_order_line_35a7b"
    _description = "Purchase Order Line (Studio)"

    x_name = fields.Char(string="Description", required=True)
    x_purchase_order_id = fields.Many2one("purchase.order", string="Commande d'achat")
    x_studio_sequence = fields.Integer(string="Séquence")


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    x_studio_one2many_field_3hq_1ih7eucbu = fields.One2many(
        "x_purchase_order_line_35a7b", "x_purchase_order_id", string="Nouvelles lignes"
    )
