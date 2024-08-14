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
             # Si un order_id est fourni, on filtre sur cette commande
            if sale_order.name == 'A24-08-02896':
                production_order = self.env['mrp.production'].search([('origin', '=', sale_order.name)], limit=1)
                
                if not production_order:
                    continue
                
                total_achat_matiere_sans_vitrage = 0.0
                total_achat_vitrage = 0.0
                
                for move in production_order.move_raw_ids:
                    vitrage_category = move.product_id.categ_id.name
                    _logger.warning('Vitrage Category for Order %s: %s', sale_order.name, vitrage_category)
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
                    'so_mcv_reel': sale_order.so_marge_brute_reel - sale_order.so_cout_mod_reel,  # Supposons que MCV = Marge brute
                    'so_prc_mcv_reel': ((sale_order.so_marge_brute_reel - sale_order.so_cout_mod_reel) / sale_order.amount_untaxed) * 100 if sale_order.amount_untaxed > 0 else 0,
                })
