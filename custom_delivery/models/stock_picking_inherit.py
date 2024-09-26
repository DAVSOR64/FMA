from odoo import models, fields

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    sale_id = fields.Many2one('sale.order', string="Sale Order")

    # Champs liés au sale.order
    so_acces_bl = fields.Char(related='sale_id.so_acces', string="Accès")
    so_type_camion_bl = fields.Char(related='sale_id.so_type_camion', string="Type de camion")
    so_horaire_ouverture_bl = fields.Char(related='sale_id.so_horaire_ouverture', string="Horaire d'ouverture")
    so_horaire_fermeture_bl = fields.Char(related='sale_id.so_horaire_fermeture', string="Horaire de fermeture")
