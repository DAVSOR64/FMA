# -*- coding: utf-8 -*-
# from odoo import http


# class CustomSaleOrder(http.Controller):
#     @http.route('/custom_sale_order/custom_sale_order', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/custom_sale_order/custom_sale_order/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('custom_sale_order.listing', {
#             'root': '/custom_sale_order/custom_sale_order',
#             'objects': http.request.env['custom_sale_order.custom_sale_order'].search([]),
#         })

#     @http.route('/custom_sale_order/custom_sale_order/objects/<model("custom_sale_order.custom_sale_order"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('custom_sale_order.object', {
#             'object': obj
#         })
