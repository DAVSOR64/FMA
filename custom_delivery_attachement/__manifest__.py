# -*- coding: utf-8 -*-
{
    'name': "custom_delivery_attachement",

    'summary': """
        Custom Delivery file excel on attachement""",

    'description': """
        Long description of module's purpose
    """,

    'author': "My Company",
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base','stock'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
        'views/delivery_report_excel_views.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
