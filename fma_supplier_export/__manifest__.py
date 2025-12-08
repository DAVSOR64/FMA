# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "Suppliers: Export (TXT)",
    "description": """
            The purpose of this module is to generate a .txt file containing supplier details.
            Crons are also introduced to generate a new file for new suppliers per day and
            move such TXT files to SFTP server.
            Task: 4061463
        """,
    "author": "Odoo PS",
    "version": "17.0.1.0.1",
    "depends": ["base_setup", "contacts"],
    "data": [
        "data/ir_cron.xml",
        "view/res_config_settings_views.xml",
        "view/res_partner_views.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": True,
}
