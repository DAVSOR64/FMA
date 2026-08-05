# -*- coding: utf-8 -*-
"""Ligne de lot : une menuiserie (ou N menuiseries identiques) d'un devis
affectee a un lot de fabrication.

C'est une table de liaison **avec quantite** : une ligne de devis portant 5
menuiseries peut etre repartie sur plusieurs lots (3 dans le lot A, 2 dans le
lot B). C'est ce qui distingue ce modele d'un simple Many2one pose sur la
ligne de devis.
"""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare


class FmaLotFabricationLine(models.Model):
    _name = "fma.lot.fabrication.line"
    _description = "Ligne de lot de fabrication"
    _order = "lot_id, sequence, id"

    sequence = fields.Integer(string="Sequence", default=10)
    lot_id = fields.Many2one(
        "fma.lot.fabrication",
        string="Lot",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        related="lot_id.company_id",
        store=True,
        index=True,
    )
    lot_state = fields.Selection(related="lot_id.state", string="Etat du lot")
    sale_line_id = fields.Many2one(
        "sale.order.line",
        string="Ligne de devis",
        required=True,
        ondelete="restrict",
        index=True,
    )
    order_id = fields.Many2one(
        related="sale_line_id.order_id",
        string="Commande",
        store=True,
        index=True,
    )
    partner_id = fields.Many2one(
        related="sale_line_id.order_id.partner_id",
        string="Client",
    )
    product_id = fields.Many2one(
        related="sale_line_id.product_id",
        string="Menuiserie",
        store=True,
    )
    product_uom_id = fields.Many2one(
        related="sale_line_id.product_uom_id",
        string="Unite",
    )
    description = fields.Text(
        # sale.order.line.name est un Text : un related doit reprendre le
        # type exact du champ source.
        related="sale_line_id.name",
        string="Designation",
    )
    product_qty = fields.Float(
        string="Quantite dans le lot",
        default=1.0,
        required=True,
        digits="Product Unit of Measure",
    )
    qty_ordered = fields.Float(
        related="sale_line_id.product_uom_qty",
        string="Quantite commandee",
    )
    production_id = fields.Many2one(
        "mrp.production",
        string="OF Assemblage",
        copy=False,
        readonly=True,
        ondelete="set null",
    )
    production_state = fields.Selection(
        related="production_id.state",
        string="Etat OF",
    )

    _product_qty_positive = models.Constraint(
        "CHECK(product_qty > 0)",
        "La quantité dans le lot doit être strictement positive.",
    )
    _lot_sale_line_uniq = models.Constraint(
        "unique(lot_id, sale_line_id)",
        "Une ligne de devis ne peut apparaître qu'une fois dans un même "
        "lot : cumulez la quantité sur une seule ligne.",
    )

    @api.constrains("sale_line_id", "product_qty")
    def _check_qty_not_over_ordered(self):
        """La somme lotee d'une ligne de devis ne peut depasser la quantite
        commandee."""
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )
        for line in self:
            sale_line = line.sale_line_id
            if not sale_line:
                continue
            total = sum(
                self.search(
                    [
                        ("sale_line_id", "=", sale_line.id),
                        ("lot_id.state", "!=", "cancel"),
                    ]
                ).mapped("product_qty")
            )
            if float_compare(
                total, sale_line.product_uom_qty, precision_digits=precision
            ) > 0:
                raise ValidationError(
                    _(
                        "Ligne %(line)s : vous avez loti %(total)s unites "
                        "alors que la commande n'en porte que %(ordered)s.",
                        line=sale_line.display_name,
                        total=total,
                        ordered=sale_line.product_uom_qty,
                    )
                )

    @api.constrains("lot_id", "sale_line_id")
    def _check_company(self):
        for line in self:
            order_company = line.sale_line_id.order_id.company_id
            if order_company and order_company != line.lot_id.company_id:
                raise ValidationError(
                    _(
                        "La commande %(order)s et le lot %(lot)s "
                        "n'appartiennent pas a la meme societe.",
                        order=line.sale_line_id.order_id.display_name,
                        lot=line.lot_id.display_name,
                    )
                )

    @api.depends("lot_id.name", "product_id")
    def _compute_display_name(self):
        for line in self:
            line.display_name = "%s / %s" % (
                line.lot_id.name or "",
                line.product_id.display_name or "",
            )
