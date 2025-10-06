from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # Taxes à facturer (TTC - HT sur la quantité à facturer, via moteur de taxes, multi-taux, positions fiscales ok)
    amount_to_invoice_tax = fields.Monetary(
        string="Taxes",
        currency_field="currency_id",
        compute="_compute_amount_to_invoice_tax",
        store=True,
        readonly=True,
    )

    # HT = TTC standard - Taxes calculées ci-dessus
    amount_to_invoice_ht = fields.Monetary(
        string="Montant à facturer HT",
        currency_field="currency_id",
        compute="_compute_amount_to_invoice_ht",
        store=True,
        readonly=True,
    )

    @api.depends(
        "order_line.qty_to_invoice",
        "order_line.price_unit",
        "order_line.discount",
        "order_line.tax_id",
        "order_line.display_type",
        "order_line.product_id",
        "currency_id",
        "partner_id",
        "fiscal_position_id",
    )
    def _compute_amount_to_invoice_tax(self):
        for order in self:
            taxes_total = 0.0
            for line in order.order_line:
                if line.display_type or not line.qty_to_invoice:
                    continue

                qty = line.qty_to_invoice or 0.0
                price_net = line.price_unit * (1.0 - (line.discount or 0.0) / 100.0)

                taxes = line.tax_id
                if order.fiscal_position_id:
                    taxes = order.fiscal_position_id.map_tax(
                        taxes, product=line.product_id, partner=order.partner_id
                    )

                res = taxes.compute_all(
                    price_net,
                    currency=order.currency_id,
                    quantity=qty,
                    product=line.product_id,
                    partner=order.partner_id,
                    is_refund=False,
                )
                taxes_total += (res.get("total_included", 0.0) - res.get("total_excluded", 0.0))

            order.amount_to_invoice_tax = taxes_total

    @api.depends("amount_to_invoice", "amount_to_invoice_tax")
    def _compute_amount_to_invoice_ht(self):
        for order in self:
            order.amount_to_invoice_ht = (order.amount_to_invoice or 0.0) - (order.amount_to_invoice_tax or 0.0)
