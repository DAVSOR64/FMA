# -*- coding: utf-8 -*-
{
    'name': 'Custom Invoice Text Block',
    'version': '1.0',
    'summary': 'Show text block on invoice based on contact boolean field',
    'author': 'Your Name',
    'depends': ['account'],
    'data': [
        'views/report_invoice.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
