from odoo import api, fields, models

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # HT à facturer par ligne = qty_to_invoice * prix unitaire net HT
    amount_to_invoice_ht_line = fields.Monetary(
        string="À facturer HT (ligne)",
        currency_field="currency_id",
        compute="_compute_amount_to_invoice_ht_line",
        store=True,
        readonly=True,
    )

    @api.depends(
        "qty_to_invoice", "price_unit", "discount",
        "display_type", "state",
    )
    def _compute_amount_to_invoice_ht_line(self):
        for line in self:
            # ignorer sections/notes
            if line.display_type:
                line.amount_to_invoice_ht_line = 0.0
                continue

            # prix unitaire net HT (sans taxes)
            net_unit = line.price_unit * (1.0 - (line.discount or 0.0) / 100.0)

            # qty_to_invoice peut être négative (retours) ; on ne veut pas majorer
            qty = line.qty_to_invoice or 0.0
            line.amount_to_invoice_ht_line = net_unit * qty


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # Somme des lignes (HT)
    amount_to_invoice_ht = fields.Monetary(
        string="Montant à facturer HT",
        currency_field="currency_id",
        compute="_compute_amount_to_invoice_ht",
        store=True,
        readonly=True,
    )

    @api.depends(
        "order_line.amount_to_invoice_ht_line",
        "order_line.display_type",
        "order_line.state",
    )
    def _compute_amount_to_invoice_ht(self):
        for order in self:
            total = sum(
                l.amount_to_invoice_ht_line
                for l in order.order_line
                if not l.display_type
            )
            order.amount_to_invoice_ht = total
