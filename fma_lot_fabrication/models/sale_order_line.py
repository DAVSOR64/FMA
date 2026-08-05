# -*- coding: utf-8 -*-
"""Vue lot sur la ligne de devis.

La ligne ne porte pas de lot en direct : elle peut etre repartie sur
plusieurs lots. On expose donc les liaisons, la quantite deja lotie et le
reste a lotir, qui pilotent le wizard de mise en lot.
"""
from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    lot_line_ids = fields.One2many(
        "fma.lot.fabrication.line",
        "sale_line_id",
        string="Lots de fabrication",
        copy=False,
    )
    lot_ids = fields.Many2many(
        "fma.lot.fabrication",
        string="Lots",
        compute="_compute_lot_info",
        store=False,
    )
    qty_lot = fields.Float(
        string="Quantite lotie",
        compute="_compute_lot_info",
        digits="Product Unit of Measure",
        help="Somme des quantites affectees a un lot de fabrication actif.",
    )
    qty_to_lot = fields.Float(
        string="Reste a lotir",
        compute="_compute_lot_info",
        digits="Product Unit of Measure",
    )
    is_lotable = fields.Boolean(
        string="A lotir",
        compute="_compute_is_lotable",
        store=True,
        help="Ligne eligible a la mise en lot : article stockable ou "
        "consommable, ni section ni note. Stocke pour rester filtrable "
        "dans les vues et les domaines.",
    )

    @api.depends(
        "lot_line_ids.product_qty",
        "lot_line_ids.lot_id.state",
        "product_uom_qty",
    )
    def _compute_lot_info(self):
        for line in self:
            active = line.lot_line_ids.filtered(
                lambda l: l.lot_id.state != "cancel"
            )
            line.lot_ids = active.mapped("lot_id")
            line.qty_lot = sum(active.mapped("product_qty"))
            line.qty_to_lot = max(line.product_uom_qty - line.qty_lot, 0.0)

    @api.depends("product_id", "product_id.type", "display_type")
    def _compute_is_lotable(self):
        for line in self:
            # En v19 les articles stockables et consommables partagent le
            # type 'consu' (le stockage est porte par is_storable) ; seuls
            # les services et les combos sont a exclure.
            line.is_lotable = bool(
                not line.display_type
                and line.product_id
                and line.product_id.type == "consu"
            )
