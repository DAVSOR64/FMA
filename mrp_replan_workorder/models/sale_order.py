# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    def action_confirm(self):
        """
        Surcharge pour déclencher la planification automatique
        après création des OFs
        """
        _logger.info("=== Validation commande %s ===", self.name)
        
        # Appel standard (crée les OFs via les règles MTO)
        res = super().action_confirm()
        
        # Récupérer les OFs créés pour cette commande
        production_orders = self.env['mrp.production'].search([
            ('origin', '=', self.name),
            ('state', 'in', ['draft', 'confirmed'])
        ])
        
        if production_orders:
            _logger.info(
                "Commande %s : %d OF(s) créé(s), lancement de la planification",
                self.name,
                len(production_orders)
            )
            
            for production in production_orders:
                # Si date de livraison définie sur la ligne de commande
                sale_line = self.order_line.filtered(
                    lambda l: l.product_id == production.product_id
                )[:1]
                
                if sale_line and sale_line.customer_lead:
                    # Calculer date de livraison = date commande + délai client
                    commitment_date = fields.Datetime.from_string(self.date_order) + \
                                    timedelta(days=sale_line.customer_lead)
                    production.commitment_date = commitment_date
                    _logger.info(
                        "OF %s : date de livraison fixée au %s",
                        production.name,
                        commitment_date.strftime('%Y-%m-%d')
                    )
                
                # Déclencher la planification
                try:
                    production.button_plan()
                    _logger.info("OF %s planifié avec succès", production.name)
                except Exception as e:
                    _logger.error(
                        "Erreur planification OF %s : %s",
                        production.name,
                        str(e)
                    )
        
        return res
