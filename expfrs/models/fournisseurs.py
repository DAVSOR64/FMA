from odoo import fields, models

class Fournisseur(models.Model):
    #_inherit = 'purchase.order'
    _name = "fournisseur"
    _description = "fournisseurs"

    #reference = fields.Char(string="Reference")
    #affaire = fields.Char(string="Affaire")
    #fournisseur = fields.Many2one('res.partner', string="Fournisseur")
    #exporte = fields.Boolean(string="Exporte")
    #date_exportation = fields.Date(string="Date Exportation")
   
    reference = fields.Char(string='Reference', required=True)
    affaire = fields.Char(string="Affaire")
    date_order = fields.Datetime(string='Date passation', required=True)
    fournisseur = fields.Many2one('res.partner', string='Fournisseur', required=True)
    order_line_ids = fields.One2many('fournisseur.order.line', 'order_id', string='Lignes commandes')
    exporte = fields.Boolean(string="Exporte")
    date_exportation = fields.Date(string="Date Exportation")
    
class FournisseurOrderLine(models.Model):
    _name = 'fournisseur.order.line'
    _description = 'Fournisseur Order Line'

    order_id = fields.Many2one('fournisseur.order', string='Order', required=True)
    product_id = fields.Many2one('product.product', string='Product', required=True)
    product_qty = fields.Float(string='Quantity', required=True)
    price_unit = fields.Float(string='Unit Price', required=True)