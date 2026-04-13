# -*- coding: utf-8 -*-
{
    'name': 'FMA - KPI Retard Atelier',
    'version': '17.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Snapshot quotidien retard/avance par poste de travail — Spreadsheet Odoo',
    'author': 'ODOVIZE',
    'depends': ['mrp', 'fma_mrp_planning'],
    'data': [
        'security/ir.model.access.csv',
        'data/cron.xml',
        'views/mrp_daily_snapshot_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
