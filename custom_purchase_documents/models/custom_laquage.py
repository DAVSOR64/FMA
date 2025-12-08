from odoo import models, fields, api


class BonLaquage(models.Model):
    _inherit = "purchase.order"

    # Ajoutez les champs spécifiques nécessaires au bon de laquage
    color = fields.Char(string="Couleur de laquage")
    quantity = fields.Float(string="Quantité à laquer")
