# -*- coding: utf-8 -*-
# from odoo import http


# class CustomDeliveryAttachement(http.Controller):
#     @http.route('/custom_delivery_attachement/custom_delivery_attachement', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/custom_delivery_attachement/custom_delivery_attachement/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('custom_delivery_attachement.listing', {
#             'root': '/custom_delivery_attachement/custom_delivery_attachement',
#             'objects': http.request.env['custom_delivery_attachement.custom_delivery_attachement'].search([]),
#         })

#     @http.route('/custom_delivery_attachement/custom_delivery_attachement/objects/<model("custom_delivery_attachement.custom_delivery_attachement"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('custom_delivery_attachement.object', {
#             'object': obj
#         })
