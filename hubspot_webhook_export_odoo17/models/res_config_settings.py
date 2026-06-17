from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    hubspot_webhook_url = fields.Char(
        string="URL Webhook HubSpot / n8n",
        config_parameter="hubspot_export.webhook_url",
        help="Exemple : https://n8n.showroom-janneau.com/webhook/fma-f2m",
    )
    hubspot_basic_auth_login = fields.Char(
        string="Identifiant Basic Auth",
        config_parameter="hubspot_export.basic_auth_login",
    )
    hubspot_basic_auth_password = fields.Char(
        string="Mot de passe Basic Auth",
        config_parameter="hubspot_export.basic_auth_password",
    )
    hubspot_export_only_updated = fields.Boolean(
        string="Exporter uniquement les créations/modifications de la veille",
        config_parameter="hubspot_export.only_updated",
        default=False,
    )
    hubspot_batch_size = fields.Integer(
        string="Taille des lots d'export",
        config_parameter="hubspot_export.batch_size",
        default=100,
        help="Nombre d'enregistrements envoyés par appel au webhook. Exemple : 100 pour envoyer les données par lots de 100.",
    )
