from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'delivery'

    def format_amount(self, amount):
        return '{:,.2f}'.format(amount).replace(',', ' ').replace('.', ',')
