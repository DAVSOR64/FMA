# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "Customer: Outstandings",
    "description": """
            The purpose of this module is add a partner field based on debit-credit difference from
            a CSV file imported from FTP server and perform related functions like filtering
            related customers and adding alerts upon sale order confirmation and validation.
            Task: 4101724
        """,
    "author": "Odoo PS",
    "version": "17.0.1.0.2",
    "depends": ["contacts", "fma_sale_order_custom"],
    "data": [
        "data/ir_cron.xml",
        "views/res_config_settings_views.xml",
        "views/res_partner_views.xml",
    ],
    "license": "LGPL-3",
}
