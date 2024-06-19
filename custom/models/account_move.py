from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    x_studio_rfrence_affaire = fields.Char(string="Custom Field affaire")
    x_studio_imputation_2 = fields.Char(string="Custom Field imputation")
    x_studio_mode_de_rglement = fields.Char(string="Custom Field mode de reglement")