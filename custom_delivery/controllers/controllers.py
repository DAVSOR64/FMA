# -*- coding: utf-8 -*-
# from odoo import http


# class CustomDelivery(http.Controller):
#     @http.route('/custom_delivery/custom_delivery', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/custom_delivery/custom_delivery/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('custom_delivery.listing', {
#             'root': '/custom_delivery/custom_delivery',
#             'objects': http.request.env['custom_delivery.custom_delivery'].search([]),
#         })

#     @http.route('/custom_delivery/custom_delivery/objects/<model("custom_delivery.custom_delivery"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('custom_delivery.object', {
#             'object': obj
#         })
