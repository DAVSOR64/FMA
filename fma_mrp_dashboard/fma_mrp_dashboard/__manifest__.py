# -*- coding: utf-8 -*-
{
    'name': 'FMA - Dashboard Capacité & Charge',
    'version': '17.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Tableau de bord capacité vs charge, GANTT planning atelier',
    'author': 'Paxo Consulting',
    'depends': ['mrp', 'planning', 'hr', 'fma_mrp_planning'],
    'data': [
        'data/mrp_macro_planning_cron.xml',
        'security/ir.model.access.csv',
        'views/capacite_charge_views.xml',
        'views/capacite_operateur_views.xml',
        'views/mrp_workorder_gantt_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
