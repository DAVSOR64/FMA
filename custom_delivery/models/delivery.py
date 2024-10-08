from odoo import models, fields, api, re

class SaleOrder(models.Model):
    _inherit = ['delivery', 'sale.order']

    def format_amount(self, amount):
        return '{:,.2f}'.format(amount).replace(',', ' ').replace('.', ',')


    line.product_id.name = re.sub(r'\[.*?\]', '', line.name).strip()
