# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = ['delivery', 'sale.order']

    def format_amount(self, amount):
        return '{:,.2f}'.format(amount).replace(',', ' ').replace('.', ',')


    # line.product_id.name = re.sub(r'\[.*?\]', '', line.name).strip()


