from odoo import api, fields, models

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # HT à facturer par ligne = total_excluded pour qty_to_invoice selon le moteur de taxes
    amount_to_invoice_ht_line = fields.Monetary(
        string="À facturer HT (ligne)",
        currency_field="currency_id",
        compute="_compute_amount_to_invoice_ht_line",
        store=True,
        readonly=True,
    )

    @api.depends(
        "qty_to_invoice",
        "price_unit",
        "discount",
        "tax_id",
        "display_type",
        "product_id",
        "company_id",
        "order_id.partner_id",
        "order_id.currency_id",
        "order_id.fiscal_position_id",
    )
    def _compute_amount_to_invoice_ht_line(self):
        for line in self:
            # ignorer sections/notes
            if line.display_type:
                line.amount_to_invoice_ht_line = 0.0
                continue

            qty = line.qty_to_invoice or 0.0
            if not qty:
                line.amount_to_invoice_ht_line = 0.0
                continue

            # prix unitaire net (remise incluse)
            price_net = line.price_unit * (1.0 - (line.discount or 0.0) / 100.0)

            # Taxes ajustées par position fiscale de la commande
            taxes = line.tax_id
            if line.order_id.fiscal_position_id:
                taxes = line.order_id.fiscal_position_id.map_tax(
                    taxes, product=line.product_id, partner=line.order_id.partner_id
                )

            # Calcul des montants pour la quantité à facturer
            res = taxes.compute_all(
                price_net,
                currency=line.order_id.currency_id,
                quantity=qty,
                product=line.product_id,
                partner=line.order_id.partner_id,
                is_refund=False,
            )
            # HT à facturer = total_excluded
            line.amount_to_invoice_ht_line = res.get("total_excluded", 0.0)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # Somme des lignes (HT à facturer)
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
    )
    def _compute_amount_to_invoice_ht(self):
        for order in self:
            order.amount_to_invoice_ht = sum(
                l.amount_to_invoice_ht_line for l in order.order_line if not l.display_type
            )
