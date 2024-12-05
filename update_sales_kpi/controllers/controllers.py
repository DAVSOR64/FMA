# -*- coding: utf-8 -*-
# from odoo import http


# class UpdateSalesKpi(http.Controller):
#     @http.route('/update_sales_kpi/update_sales_kpi', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/update_sales_kpi/update_sales_kpi/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('update_sales_kpi.listing', {
#             'root': '/update_sales_kpi/update_sales_kpi',
#             'objects': http.request.env['update_sales_kpi.update_sales_kpi'].search([]),
#         })

#     @http.route('/update_sales_kpi/update_sales_kpi/objects/<model("update_sales_kpi.update_sales_kpi"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('update_sales_kpi.object', {
#             'object': obj
#         })
