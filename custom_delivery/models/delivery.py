from odoo import models, fields, api, re

class SaleOrder(models.Model):
    _inherit = ['delivery', 'sale.order']

    def format_amount(self, amount):
        return '{:,.2f}'.format(amount).replace(',', ' ').replace('.', ',')


    line.product_id.name = re.sub(r'\[.*?\]', '', line.name).strip()

    # Création d'un champ calculé pour le reliquat
    reliquat_qty = fields.Float(string="Reliquat", compute='_compute_reliquat_qty', store=True)

    @api.depends('product_uom_qty', 'quantity_done')
    def _compute_reliquat_qty(self):
        for move in self:
            move.reliquat_qty = move.product_uom_qty - move.quantity_done
