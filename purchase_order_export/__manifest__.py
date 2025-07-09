# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Purchase Order : Export (XML)',
    'description':
        """
            The purpose of this module is to export the Purchase Order details in XML format.
            A cron is also introduced to move such XML files to SFTP server.
            Task: 3975517
        """,
    'author': 'Odoo PS',
    'version': '17.0.0.2.0',
    'depends': [
        'purchase', 'stock'
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'data/purchase_order_export.xml',
        'data/purchase_order_export_template_v2.xml',
        'views/product_views.xml',
        'views/purchase_order_views.xml',
        'views/res_config_settings.xml',
        'views/res_partner.xml',
        'wizard/po_export_wizard_view.xml',
    ],
    'license': 'LGPL-3',
}
