from odoo import models, fields, api

class AccountMove(models.Model):
    _inherit = 'account.move'

    show_text_block = fields.Boolean(string="Show Text Block", compute='_compute_show_text_block')

    @api.depends('partner_id')
    def _compute_show_text_block(self):
        for record in self:
            record.show_text_block = record.partner_id.x_studio_affacturage

    @api.model
    def _get_invoice_lines(self):
        lines = super(AccountMove, self)._get_invoice_lines()
        return lines.filtered(lambda l: l.product_id.name != 'Devis')

    #discount_rate = fields.Float(string='Discount Rate', compute='_compute_discount_rate', store=True)
    #amount_discount = fields.Monetary(string='Total Discount', compute='_compute_amount_discount', store=True)
    #amount_advance = fields.Monetary(string='Advance Payment', compute='_compute_amount_advance', store=True)

    #@api.depends('invoice_line_ids.sale_line_ids.discount', 'invoice_line_ids.sale_line_ids.price_subtotal')
    #def _compute_discount_rate(self):
    #    for move in self:
    #        total_discount = sum(line.sale_line_ids.price_subtotal * (line.sale_line_ids.discount / 100.0) for line in move.invoice_line_ids)
    #        if move.amount_untaxed:
    #            move.discount_rate = (total_discount / move.amount_untaxed) * 100
    #        else:
    #            move.discount_rate = 0.0

    #@api.depends('invoice_line_ids.sale_line_ids.discount', 'invoice_line_ids.sale_line_ids.price_subtotal')
    #def _compute_amount_discount(self):
    #    for move in self:
    #        move.amount_discount = sum(line.sale_line_ids.price_subtotal * (line.sale_line_ids.discount / 100.0) for line in move.invoice_line_ids)

    #@api.depends('invoice_line_ids.sale_line_ids.order_id.advance_payment')
    #def _compute_amount_advance(self):
    #    for move in self:
    #        move.amount_advance = sum(line.sale_line_ids.order_id.advance_payment for line in move.invoice_line_ids if line.sale_line_ids.order_id)