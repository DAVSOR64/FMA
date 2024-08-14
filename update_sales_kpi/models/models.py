# -*- coding: utf-8 -*-

# from odoo import models, fields, api


# class update_sales_kpi(models.Model):
#     _name = 'update_sales_kpi.update_sales_kpi'
#     _description = 'update_sales_kpi.update_sales_kpi'

#     name = fields.Char()
#     value = fields.Integer()
#     value2 = fields.Float(compute="_value_pc", store=True)
#     description = fields.Text()
#
#     @api.depends('value')
#     def _value_pc(self):
#         for record in self:
#             record.value2 = float(record.value) / 100
