from odoo import models, fields

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_studio_ref_affaire = fields.Char(string="Custom Field")

    def _prepare_invoice(self):
        invoice_vals = super(SaleOrder, self)._prepare_invoice()
        invoice_vals['x_studio_rfrence_affaire'] = self.x_studio_ref_affaire
        return invoice_vals
