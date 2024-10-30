# -*- coding: utf-8 -*-
{
    'name': 'Custom Field Transfer',
    'version': '15.0',
    'summary': 'Created and Transfer custom field from contact and sale order to invoice',
    'author': 'Your Name',
    'depends': ['base','sale', 'account','contacts', 'sale_stock'],
    'data': [
        'views/res_partner_views.xml',
        'views/sale_order_views.xml',
        'views/account_move_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'custom/static/src/css/custom_styles.css',  # Chemin vers votre fichier CSS
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
