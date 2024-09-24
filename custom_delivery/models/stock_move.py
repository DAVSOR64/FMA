from odoo import models, fields, api
import re

class StockMove(models.Model):
    _inherit = 'stock.move'

    cleaned_description = fields.Char(string="Description Sans Crochets", compute='_compute_cleaned_description')

    @api.depends('name')
    def _compute_cleaned_description(self):
        for move in self:
            if move.name:
                # Enlever le texte entre crochets dans la description
                move.cleaned_description = re.sub(r'\[.*?\]', '', move.name).strip()
            else:
                move.cleaned_description = move.name
