from odoo import models, fields, api
from odoo.exceptions import UserError

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    


    @api.model
    def update_sales_order_fields(self):
        sale_orders = self.search([])  # Vous pouvez ajouter un domaine pour filtrer les commandes de vente

        for sale_order in sale_orders:
            production_order = self.env['mrp.production'].search([('origin', '=', sale_order.name)], limit=1)
            
            if not production_order:
                continue
            
            total_achat_matiere_sans_vitrage = 0.0
            total_achat_vitrage = 0.0
            
            for move in production_order.move_raw_ids:
                if move.product_id.categ_id.name <> 'All / Vitrage':  # Catégorie ou autre critère pour identifier
                    total_achat_matiere_sans_vitrage += move.product_id.standard_price * move.product_uom_qty
                elif move.product_id.categ_id.name == 'All / Vitrage':
                    total_achat_vitrage += move.product_id.standard_price * move.product_uom_qty
            
            sale_order.write({
                'so_achat_matiere_reel': total_achat_matiere_sans_vitrage,
                'so_achat_vitrage_reel': total_achat_vitrage,
                'so_montant_facturer_reel': sale_order.amount_total,
                'so_marge_brute_reel': sale_order.amount_total - (total_achat_matiere_sans_vitrage + total_achat_vitrage + sale_order.mod),
                'so_prc_marge_brute_reel': ((sale_order.amount_total - (total_achat_matiere_sans_vitrage + total_achat_vitrage + sale_order.mod)) / sale_order.amount_total) * 100 if sale_order.amount_total > 0 else 0,
                'so_mcv_reel': sale_order.amount_total - (total_achat_matiere_sans_vitrage + total_achat_vitrage + sale_order.mod),  # Supposons que MCV = Marge brute
                'so_prc_mcv_reel': ((sale_order.amount_total - (total_achat_matiere_sans_vitrage + total_achat_vitrage + sale_order.mod)) / sale_order.amount_total) * 100 if sale_order.amount_total > 0 else 0,
            })
