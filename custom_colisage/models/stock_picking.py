from odoo import models, fields

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    so_acces_bl = fields.Char(string="Accès")

    so_horaire_ouverture_bl = fields.Float(string='Horaire ouverture', widget='float_time')
    so_horaire_fermeture_bl = fields.Float(string='Horaire fermeture', widget='float_time')

    so_type_camion_bl = fields.Selection(
        [
            ('Semi-remorque (base)', 'Semi-remorque (base)'),
            ('Semi-remorque avec hayon (base)', 'Semi-remorque avec hayon (base)'),
            ('Semi-remorque plateau (base)', 'Semi-remorque plateau (base)'),
            ('Porteur avec hayon (base)', 'Porteur avec hayon (base)'),
            ('Fourgon 20m3 (150€ + 0.50€/km)', 'Fourgon 20m3 (150€ + 0.50€/km)'),
            ('Semi-remorque chariot embarqué (650€)', 'Semi-remorque chariot embarqué (650€)'),
            ('Autre (sur devis)', 'Autre (sur devis)'),
        ],
        string="Type de camion (Hayon palette maxi 2400mm)",
    )
