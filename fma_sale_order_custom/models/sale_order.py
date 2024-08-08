# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    date_bpe = fields.Datetime("Date BPE")
    state = fields.Selection(
        selection_add = [
            ('validated', 'Devis Validé'),
            ('sale', )
        ])

    def action_validation(self):
        for order in self:
            order.state = 'validated'
            order.x_studio_date_de_la_commande = fields.datetime.today()

    def action_confirm(self):
        for order in self:
            order.date_bpe = fields.datetime.today()
        return super().action_confirm()
