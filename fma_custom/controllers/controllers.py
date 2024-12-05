# -*- coding: utf-8 -*-
# from odoo import http


# class FmaCustom(http.Controller):
#     @http.route('/fma_custom/fma_custom', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/fma_custom/fma_custom/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('fma_custom.listing', {
#             'root': '/fma_custom/fma_custom',
#             'objects': http.request.env['fma_custom.fma_custom'].search([]),
#         })

#     @http.route('/fma_custom/fma_custom/objects/<model("fma_custom.fma_custom"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('fma_custom.object', {
#             'object': obj
#         })
