from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    advance_payment = fields.Monetary(string='Advance Payment', compute='_compute_advance_payment', store=True)

    @api.depends('order_line.price_total')
    def _compute_advance_payment(self):
        for order in self:
            order.advance_payment = sum(line.price_subtotal for line in order.order_line)

