from odoo import fields, models, _


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    sftp_server_host = fields.Char(
        config_parameter="fma_powerbi_export.sftp_server_host"
    )
    sftp_server_username = fields.Char(
        config_parameter="fma_powerbi_export.sftp_server_username"
    )
    sftp_server_password = fields.Char(
        config_parameter="fma_powerbi_export.sftp_server_password"
    )
    sftp_server_file_path = fields.Char(
        config_parameter="fma_powerbi_export.sftp_server_file_path"
    )


    def action_generate_powerbi_files(self):
        self.ensure_one()
        self.env["export.sftp.scheduler"].sudo().cron_generate_files()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Export Power BI"),
                "message": _("Les fichiers Power BI ont été générés en pièces jointes et dans le dossier temporaire."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_send_powerbi_files_to_sftp(self):
        self.ensure_one()
        self.env["export.sftp.scheduler"].sudo().cron_send_files_to_sftp()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Export Power BI"),
                "message": _("Envoi SFTP lancé. Consultez les logs pour le détail."),
                "type": "success",
                "sticky": False,
            },
        }
