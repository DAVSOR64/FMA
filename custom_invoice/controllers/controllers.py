# -*- coding: utf-8 -*-
# from odoo import http


# class CustomInvoice(http.Controller):
#     @http.route('/custom_invoice/custom_invoice', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/custom_invoice/custom_invoice/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('custom_invoice.listing', {
#             'root': '/custom_invoice/custom_invoice',
#             'objects': http.request.env['custom_invoice.custom_invoice'].search([]),
#         })

#     @http.route('/custom_invoice/custom_invoice/objects/<model("custom_invoice.custom_invoice"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('custom_invoice.object', {
#             'object': obj
#         })
