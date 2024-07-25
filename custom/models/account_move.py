from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    x_studio_rfrence_affaire = fields.Char(string="Affaire")
    x_studio_imputation_2 = fields.Char(string="Référence Commande")
    x_studio_delegation_fac = fields.Boolean(string="Déléagtion")
    x_studio_com_delegation_fac = fields.Char(string="COmmentaire Délégation :")
    x_studio_mode_de_rglement = fields.Char(string="Mode de réglement")