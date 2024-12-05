import logging
from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    @api.model
    def update_sales_order_fields(self):
        sale_orders = self.search([])  # Vous pouvez ajouter un domaine pour filtrer les commandes de vente
        
        for sale_order in sale_orders:

            total_achat_matiere_sans_vitrage = 0.0
            total_achat_vitrage = 0.0    
            for line in sale_order.order_line:
                # Si un order_id est fourni, on filtre sur cette commande
                category_name = line.product_id.categ_id.name
                if category_name.startswith('ALU') or category_name.startswith('ACI'):
                    continue
                
                production_order = self.env['mrp.production'].search([
                        ('product_id', '=', line.product_id.id),
                        ('origin', '=', sale_order.name)
                    ], limit=1)
    
                #_logger.warning('  Number Order %s:', sale_order.name)
                if not production_order:
                    #_logger.warning(' Order %s:', sale_order.name)
                    if line.product_id.categ_id.name != 'Vitrage':
                        #_logger.warning('Price Order %s:', str(line.product_id.standard_price))
                        total_achat_matiere_sans_vitrage += line.product_id.standard_price * line.product_uom_qty
                    else:
                        #_logger.warning('Price sans vitrage Order %s:', str(line.product_id.standard_price))
                        total_achat_vitrage += line.product_id.standard_price * line.product_uom_qty
                else :        
                    for move in production_order.move_raw_ids:
                        #vitrage_category = move.product_id.categ_id.name
                        #_logger.warning('Vitrage Category for Order %s: %s', sale_order.name, vitrage_category)
                        if move.product_id.categ_id.name != 'Vitrage':  # Catégorie ou autre critère pour identifier
                            total_achat_matiere_sans_vitrage += move.product_id.standard_price * move.product_uom_qty
                        elif move.product_id.categ_id.name == 'Vitrage':
                            total_achat_vitrage += move.product_id.standard_price * move.product_uom_qty
                
            sale_order.write({
                'so_achat_matiere_reel': total_achat_matiere_sans_vitrage,
                'so_achat_vitrage_reel': total_achat_vitrage,
                'so_mtt_facturer_reel': sale_order.amount_untaxed,
                'so_marge_brute_reel': sale_order.amount_untaxed - (total_achat_matiere_sans_vitrage + total_achat_vitrage),
                'so_prc_marge_brute_reel': ((sale_order.amount_untaxed - (total_achat_matiere_sans_vitrage + total_achat_vitrage)) / sale_order.amount_untaxed) * 100 if sale_order.amount_untaxed > 0 else 0,
                'so_mcv_reel': sale_order.amount_untaxed - (total_achat_matiere_sans_vitrage + total_achat_vitrage) - sale_order.so_cout_mod_reel,  # Supposons que MCV = Marge brute
                'so_prc_mcv_reel': ((sale_order.amount_untaxed - (total_achat_matiere_sans_vitrage + total_achat_vitrage) - sale_order.so_cout_mod_reel) / sale_order.amount_untaxed) * 100 if sale_order.amount_untaxed > 0 else 0,
            })
