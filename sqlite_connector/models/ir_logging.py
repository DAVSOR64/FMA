from odoo import models, fields, _


class IrLogging(models.Model):
    _inherit = 'ir.logging'


    connector_id = fields.Many2one('sqlite.connector')
