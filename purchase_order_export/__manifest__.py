# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Purchase Order : Export (XML)',
    'description':
        """
            The purpose of this module is to export the Purchase Order details in XML format.
            A cron is also introduced to move such XML files to FTP server.
            Task: 3975517
        """,
    'author': 'Odoo PS',
    'version': '17.0.1.0.1',
    'depends': [
        'purchase', 'stock'
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'data/purchase_order_export.xml',
        'views/purchase_order_views.xml',
        'views/res_config_settings.xml',
        'views/res_partner.xml'
    ],
    'license': 'LGPL-3',
}
