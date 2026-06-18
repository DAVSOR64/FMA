# -*- coding: utf-8 -*-
from odoo import models, fields


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    laquage_production_id = fields.Many2one(
        'mrp.production',
        string='OF laquage',
        copy=False,
        index=True,
        help="OF F2M à l'origine de cette commande de sous-traitance laquage.",
    )


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    laquage_production_id = fields.Many2one(
        'mrp.production',
        string='OF laquage',
        copy=False,
        index=True,
        help="OF F2M à l'origine de cette ligne de sous-traitance laquage.",
    )
