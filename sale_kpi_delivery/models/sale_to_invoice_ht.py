from odoo import api, fields, models

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # Optionnel : utile pour la liste des lignes, mais ne doit PAS être utilisé par le compute de la commande
    amount_to_invoice_ht_line = fields.Monetary(
        string="À facturer HT (ligne)",
        currency_field="currency_id",
        compute="_compute_amount_to_invoice_ht_line",
        store=True,
        readonly=True,
    )

    @api.depends("price_subtotal", "product_uom_qty", "qty_to_invoice", "display_type")
    def _compute_amount_to_invoice_ht_line(self):
        for line in self:
            if line.display_type or not line.product_uom_qty:
                line.amount_to_invoice_ht_line = 0.0
            else:
                ratio = max(line.qty_to_invoice, 0.0) / line.product_uom_qty
                line.amount_to_invoice_ht_line = line.price_subtotal * ratio


class SaleOrder(models.Model):
    _inherit = "sale.order"

    amount_to_invoice_ht = fields.Monetary(
        string="Montant à facturer HT",
        currency_field="currency_id",
        compute="_compute_amount_to_invoice_ht",
        store=True,
        readonly=True,
    )

    # ⚠️ IMPORTANT : ne dépend plus du champ amount_to_invoice_ht_line (qui n’existe pas encore à l’init)
    @api.depends(
        "order_line.price_subtotal",
        "order_line.product_uom_qty",
        "order_line.qty_to_invoice",
        "order_line.display_type",
    )
    def _compute_amount_to_invoice_ht(self):
        for order in self:
            total = 0.0
            for l in order.order_line:
                if l.display_type or not l.product_uom_qty:
                    continue
                ratio = max(l.qty_to_invoice, 0.0) / l.product_uom_qty
                total += l.price_subtotal * ratio
            order.amount_to_invoice_ht = total
