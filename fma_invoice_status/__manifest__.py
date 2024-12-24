# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Invoice: Status Update',
    'description':
        """
            The purpose of this module is update the status and date of payment of the
            invoices from a CSV file imported from FTP server.
            Task: 4115364
        """,
    'author': 'Odoo PS',
    'version': '15.0.0.1.0',
    'depends': [
        'account_accountant'
    ],
    'data': [
        'data/ir_cron.xml',
        'views/res_config_settings_views.xml',
    ],
    'license': 'LGPL-3',
}
