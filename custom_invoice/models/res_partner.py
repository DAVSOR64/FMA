from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_studio_affacturage = fields.Boolean(string="Show Text Block")
