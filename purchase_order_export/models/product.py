# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"


    clc1 = fields.Char(string="Clc1")
    clc2 = fields.Char(string="Clc2")
    cls1 = fields.Char(string="Cls1")
    cls2 = fields.Char(String="Cls2")
