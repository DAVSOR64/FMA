from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_studio_mode_de_rglement_1 = fields.Char(string="Mode de Règlement")
    
    def _prepare_order(self):
        order_vals = super(ResPartner, self)._prepare_order()
        order_vals['x_studio_mode_de_rglement'] = self.x_studio_mode_de_rglement_1
        return order_vals