from odoo import models, fields

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_studio_ref_affaire = fields.Char(string="Custom Field affaire")
    x_studio_imputation = fields.Char(string="Custom Field imputation")
    x_studio_mode_de_rglement = fields.Char(string="Custom Field mode de reglement")
    
    def _prepare_invoice(self):
        invoice_vals = super(SaleOrder, self)._prepare_invoice()
        invoice_vals['x_studio_rfrence_affaire'] = self.x_studio_ref_affaire
        invoice_vals['x_studio_imputation_2'] = self.x_studio_imputation
        invoice_vals['x_studio_mode_de_rglement'] = self.x_studio_mode_de_rglement
        return invoice_vals
