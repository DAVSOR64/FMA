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
    #
    # Char et non Date : res.config.settings n'accepte que boolean, integer,
    # float, char, selection, many2one et datetime. Un champ Date y fait
    # echouer l'ouverture meme des reglages -- « must have type ... » -- et la
    # valeur part de toute facon en texte dans ir.config_parameter.
    powerbi_mouvements_depuis = fields.Char(
        string="Mouvements de stock depuis",
        config_parameter="export_powerbi.mouvements_depuis",
        help="Format AAAA-MM-JJ. Vide = 1er janvier 2025.",
    )
    powerbi_mouvements_perimetre = fields.Selection(
        [
            ("production", "Fabrication et ventes seulement"),
            ("tous", "Tous les mouvements"),
        ],
        string="Périmètre des mouvements",
        config_parameter="export_powerbi.mouvements_perimetre",
        default="production",
        help="« Fabrication et ventes » ne retient que les mouvements lies a "
        "un ordre de fabrication ou a une commande : ce sont les seuls qui "
        "repondent a la question de l'en-cours. Les receptions fournisseur, "
        "les inventaires et les transferts internes sans rapport sont "
        "ecartes. « Tous » exporte la totalite, au prix du volume.",
    )
