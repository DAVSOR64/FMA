# -*- coding: utf-8 -*-

# from odoo import models, fields, api


# class custom_delivery_attachement(models.Model):
#     _name = 'custom_delivery_attachement.custom_delivery_attachement'
#     _description = 'custom_delivery_attachement.custom_delivery_attachement'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100
