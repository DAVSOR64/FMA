# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Supplier: Export (TXT)',
    'description':
        """
            The purpose of this module is to generate a .txt file containing supplier details.
            Crons are also introduced to generate a new file for new supplier per day and
            move such TXT files to SFTP server.
        """,
    'author': 'Odoo PS',
    'version': '17.0.1.0.1',
    'depends': [
        'base_setup',
        'contacts'
    ],
    'data': [
        'data/ir_cron.xml',
        'views/res_config_settings_views.xml',
        'views/res_partner_views.xml'
    ],
    'license': 'LGPL-3',
}
