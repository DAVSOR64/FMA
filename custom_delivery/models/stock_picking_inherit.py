from odoo import models, fields

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # Champs liés au sale.order
    so_acces = fields.Char(related='sale_order_id.so_acces', string="Accès")
    so_type_camion = fields.Char(related='sale_order_id.so_type_camion', string="Type de camion")
    so_horaire_ouverture = fields.Char(related='sale_order_id.so_horaire_ouverture', string="Horaire d'ouverture")
    so_horaire_fermeture = fields.Char(related='sale_order_id.so_horaire_fermeture', string="Horaire de fermeture")
