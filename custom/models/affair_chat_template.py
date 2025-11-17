from odoo import models, fields

class AffairChatTemplate(models.Model):
    _name = 'affair.chat.template'
    _description = "Modèle de message pour le chat sur les affaires"

    name = fields.Char(string="Nom du modèle", required=True)
    code = fields.Char(string="Code interne")
    body = fields.Html(string="Message", required=True)
    active = fields.Boolean(default=True)
