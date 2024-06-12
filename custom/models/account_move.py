from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    x_studio_rfrence_affaire = fields.Char(string="Custom Field")
