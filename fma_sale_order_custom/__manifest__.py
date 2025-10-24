# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Sale Order Customization',
    'description':
        """
            The purpose of this module is add a new state 'Devis Validé' between QUOTATION and SALES ORDER
            with a new action "Validation" and perform actions on its related fields on the sales order.
            Task: 4098688
        """,
    'author': 'Odoo PS',
    'version': '17.0.1.0.1',
    'depends': [
        'sale_management',
        'custom',
        
    ],
    'data': [
        'views/sale_order_views.xml'
    ],
    'license': 'LGPL-3',
}
