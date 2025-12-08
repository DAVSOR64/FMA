from odoo import fields, models


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
