from odoo import models, fields

class ExportSFTPConfig(models.Model):
    _name = 'export.sftp.config'
    _description = 'Configuration SFTP pour export Power BI'

    host = fields.Char('Hôte SFTP', required=True)
    port = fields.Integer('Port', default=22)
    username = fields.Char('Utilisateur', required=True)
    password = fields.Char('Mot de passe', required=True)
    path = fields.Char('Répertoire distant', default='/')
