# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Customers: Export (TXT)',
    'description':
        """
            The purpose of this module is to generate a .txt file containing customer details.
            Crons are also introduced to generate a new file for new customers per day and
            move such TXT files to FTP server.
            Task: 4061463
        """,
    'author': 'Odoo PS',
    'version': '15.0.0.1.0',
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
