# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': "custom_sale_order",

    'summary': """
        Custome doc sale order""",

    'description': """
        This modul customize the sale_order odf
    """,

    'author': "Odoo PS",
    'category': 'Uncategorized',
    'version': '17.0.1.0.1',

    # any module necessary for this one to work correctly
    'depends': ['sale'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        #'views/views.xml',
        'views/sales_order.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',

}
