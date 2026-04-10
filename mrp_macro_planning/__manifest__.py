# -*- coding: utf-8 -*-
{
    'name': 'MRP Macro Planning',
    'version': '17.0.1.0.0',
    'summary': 'Macro planning based on work orders macro dates',
    'category': 'Manufacturing',
    'author': 'OpenAI',
    'license': 'LGPL-3',
    'depends': ['mrp', 'web_gantt'],
    'data': [
        'views/mrp_workorder_gantt_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
}
