from odoo import models, fields

import logging

_logger = logging.getLogger(__name__)

class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_studio_affacturage = fields.Boolean(string="Show Text Block")
    
