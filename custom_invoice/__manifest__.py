# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Custom Invoice Text Block',
    'version': '17.0.1.0.1',
    'summary': 'Show text block on invoice based on contact boolean field',
    'author': 'Odoo PS',
    'depends': ['account', 'custom'],
    'data': [
         'views/report_invoice.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
