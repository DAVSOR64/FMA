from odoo import fields, models

class Fournisseur(models.Model):
    _name = "expfrs.fournisseur"
    _description = "fournisseurs"

    name = fields.Many2one('res.partner', string="Fournisseur")
    code = fields.Char("Référence")
    numero  = fields.Char("Numéro")
    