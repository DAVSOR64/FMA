# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api
from datetime import datetime

class MrpProduction(models.Model):
    _inherit = 'mrp.production'
    
    def button_mark_done(self):
        # Appel de la méthode d'origine pour valider l'ordre de production
        res = super(MrpProduction, self).button_mark_done()
        
        # Vérifiez si l'ordre de production a une référence vers un devis
        if self.origin:
            # Recherche du devis correspondant en fonction de l'origine (nom de l'ordre de vente)
            sale_order = self.env['sale.order'].search([('name', '=', self.origin)], limit=1)
            if sale_order:
                # Mettez à jour le champ de date avec la date actuelle
                sale_order.write({'so_date_de_fin_de_production_reel': datetime.now()})
        
        return res
