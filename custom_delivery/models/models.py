# -*- coding: utf-8 -*-

# from odoo import models, fields, api


# class custom_delivery(models.Model):
#     _name = 'custom_delivery.custom_delivery'
#     _description = 'custom_delivery.custom_delivery'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100
class StockPicking(models.Model):
    _inherit = 'stock.picking'

    so_acces = fields.Char(related='sale_id.so_acces', string="Accès")
    so_type_camion = fields.Char(related='sale_id.so_type_camion', string="Type de camion")
    so_horaire_ouverture = fields.Char(related='sale_id.so_horaire_ouverture', string="Horaire d'ouverture")
    so_horaire_fermeture = fields.Char(related='sale_id.so_horaire_fermeture', string="Horaire de fermeture")
