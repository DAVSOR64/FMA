# -- coding: utf-8 --
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    # extra fields
    x_studio_ref_int_logikal = fields.Char()
    x_studio_unit_logikal = fields.Char()
    x_studio_color_logikal = fields.Char()
    x_studio_largeur_mm = fields.Integer()
    x_studio_longueur_m = fields.Integer()
