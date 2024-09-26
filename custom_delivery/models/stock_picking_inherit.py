from odoo import models, fields

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    sale_order_id = fields.Many2one('sale.order', string="Sale Order", related='group_id.sale_id', store=True)
