# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "Invoices: Export (CSV)",
    "description": """
            The purpose of this module is to create the .csv file for invoices with the details of journal items.
            A cron is also introduced to move such CSV and invoice PDF files to FTP server.
            Task: 4022500
        """,
    "author": "Odoo PS",
    "version": "17.0.1.0.1",
    "depends": ["account_accountant", "sale_management", "custom"],
    "data": [
        "data/ir_cron.xml",
        "views/account_move_views.xml",
        "views/res_config_settings.xml",
    ],
    "license": "LGPL-3",
}
