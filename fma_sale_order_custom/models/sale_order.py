# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    date_bpe = fields.Date(string="Date BPE") 

# Init date validation devis

    def action_validation(self):
        for order in self:
            order.state = 'validated'
            order.x_studio_date_de_la_commande = fields.datetime.today()
            order.so_date_devis_valide = fields.datetime.today()
            
 # Init date BPE lors de la confirmation du devis
    def action_confirm(self):
        for order in self:
            order.so_date_bpe = fields.datetime.today()
        return super().action_confirm()
        
 # Init date de modification devis
    def action_quotation_send(self):
        for order in self:
            order.so_date_de_modification_devis =fields.Date.today()
