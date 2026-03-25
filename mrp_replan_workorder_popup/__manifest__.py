# -*- coding: utf-8 -*-
{
    'name': 'MRP Replan Workorder Popup',
    'version': '18.0.1.0.0',
    'summary': 'Popup de prévisualisation pour la replanification OF',
    'depends': ['mrp', 'purchase_stock', 'mrp_replan_workorder'],
    'data': [
        'security/ir.model.access.csv',
        'views/mrp_replan_preview_wizard_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
