# -*- coding: utf-8 -*-
# from odoo import http


# class Expfrs(http.Controller):
#     @http.route('/expfrs/expfrs', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/expfrs/expfrs/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('expfrs.listing', {
#             'root': '/expfrs/expfrs',
#             'objects': http.request.env['expfrs.expfrs'].search([]),
#         })

#     @http.route('/expfrs/expfrs/objects/<model("expfrs.expfrs"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('expfrs.object', {
#             'object': obj
#         })

