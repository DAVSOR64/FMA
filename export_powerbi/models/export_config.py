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
    # Point de depart de l'export des mouvements de stock. Parametre et non
    # fige dans le code : reculer ou avancer cette date ne doit pas demander
    # une livraison.
    powerbi_mouvements_depuis = fields.Date(
        string="Mouvements de stock depuis",
        config_parameter="export_powerbi.mouvements_depuis",
    )
