from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    x_studio_rfrence_affaire = fields.Char(string="Affaire")
    x_studio_imputation_2 = fields.Char(string="Référence Commande Client")
    x_studio_delegation_fac = fields.Boolean(string="Déléagtion")
    x_studio_com_delegation_fac = fields.Char(string="Commentaire Délégation :")
    x_studio_mode_de_rglement = fields.Char(string="Mode de réglement")
    x_studio_related_field_m8sZb = fields.Char(string="test")
    x_studio_mode_de_rglement_1 = fields.Char(string="Mode de réglement")

    inv_mode_de_reglement = fields.Selection(related='partner_id.part_mode_de_reglement', string="Mode de Règlement")
    inv_code_tiers = fields.Integer(related='partner_id.part_code_tiers', string="Code Tiers")
    #inv_commande_client = fields.Char(related='invoice_origin.so_commande_client', string="N° Commande Client")
    inv_affacturage = fields.Boolean(related='partner_id.part_affacturage', string="Affacturage")
    #inv_delegation = fields.Boolean(related='invoice_origin.so_delegation', string="Délégation")
    #inv_commentaire_delegation = fields.Char(related='invoice_origin.so_commentaire_delegation', string="Commentaire Délégation")