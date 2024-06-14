# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Purchase Order : Export',
    'description':
    """
        Attach an XML file to purchase orders and send the XML file to the FTP server using cron.
        Task: 3975517
    """,
    'depends': [
        'purchase'
    ],
    'data': [
        'data/export_purchase_order_cron.xml',
        'views/purchase_views.xml',
        'views/res_config_settings.xml',
        'report/purchase_order_export_template.xml'
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
