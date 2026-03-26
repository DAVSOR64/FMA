# -*- coding: utf-8 -*-
{
    'name': 'MRP Batch Macro Replan',
    'version': '17.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Recalcul batch du macro planning des OF non démarrés',
    'author': 'OpenAI',
    'license': 'LGPL-3',
    'depends': [
        'mrp_replan_workorder',
        'mrp_macro_planning',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/mrp_batch_macro_replan_views.xml',
    ],
    
    'installable': True,
    'application': False,
}
