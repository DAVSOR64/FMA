from odoo import models, fields, api

class AccountMove(models.Model):
    _inherit = 'account.move'

    show_text_block = fields.Boolean(string="Show Text Block", compute='_compute_show_text_block')

    @api.depends('partner_id')
    def _compute_show_text_block(self):
        for record in self:
            record.show_text_block = record.partner_id.x_studio_affacturage
