from odoo import api, fields, models

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # Taxes à facturer par ligne (sur la quantité à facturer)
    amount_to_invoice_tax_line = fields.Monetary(
        string="Taxes à facturer (ligne)",
        currency_field="currency_id",
        compute="_compute_amount_to_invoice_tax_line",
        store=True,
        readonly=True,
    )

    @api.depends(
        "qty_to_invoice", "price_unit", "discount", "tax_id", "display_type",
        "product_id", "company_id",
        "order_id.partner_id", "order_id.currency_id", "order_id.fiscal_position_id",
    )
    def _compute_amount_to_invoice_tax_line(self):
        for line in self:
            if line.display_type or not line.qty_to_invoice:
                line.amount_to_invoice_tax_line = 0.0
                continue

            qty = line.qty_to_invoice or 0.0
            price_net = line.price_unit * (1.0 - (line.discount or 0.0) / 100.0)

            taxes = line.tax_id
            if line.order_id.fiscal_position_id:
                taxes = line.order_id.fiscal_position_id.map_tax(
                    taxes, product=line.product_id, partner=line.order_id.partner_id
                )

            res = taxes.compute_all(
                price_net,
                currency=line.order_id.currency_id,
                quantity=qty,
                product=line.product_id,
                partner=line.order_id.partner_id,
                is_refund=False,
            )
            # Taxes = TTC - HT
            line.amount_to_invoice_tax_line = (res.get("total_included", 0.0) - res.get("total_excluded", 0.0))


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # Taxes à facturer au niveau commande (somme des lignes)
    amount_to_invoice_tax = fields.Monetary(
        string="Taxes",
        currency_field="currency_id",
        compute="_compute_amount_to_invoice_tax",
        store=True,
        readonly=True,
    )

    # Montant à facturer HT = TTC standard - Taxes calculées ci-dessus
    amount_to_invoice_ht = fields.Monetary(
        string="Montant à facturer HT",
        currency_field="currency_id",
        compute="_compute_amount_to_invoice_ht",
        store=True,
        readonly=True,
    )

    @api.depends("order_line.amount_to_invoice_tax_line", "order_line.display_type")
    def _compute_amount_to_invoice_tax(self):
        for order in self:
            order.amount_to_invoice_tax = sum(
                l.amount_to_invoice_tax_line for l in order.order_line if not l.display_type
            )

    @api.depends("amount_to_invoice", "amount_to_invoice_tax")
    def _compute_amount_to_invoice_ht(self):
        for order in self:
            # 'amount_to_invoice' est le TTC standard d'Odoo
            order.amount_to_invoice_ht = (order.amount_to_invoice or 0.0) - (order.amount_to_invoice_tax or 0.0)
