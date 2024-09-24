from odoo import models, fields

class StockMove(models.Model):
    _inherit = 'stock.move'

    cleaned_description = fields.Char(string="Description Sans Crochets", compute='_compute_cleaned_description')

    def _compute_cleaned_description(self):
        for move in self:
            # Enlever le texte entre crochets
            if move.name:
                move.cleaned_description = re.sub(r'\[.*?\]', '', move.name)
            else:
                move.cleaned_description = move.name
