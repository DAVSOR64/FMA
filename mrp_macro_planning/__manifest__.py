# -*- coding: utf-8 -*-
{
    'name': 'MRP Macro Planning - Capacité vs Charge',
    'version': '17.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Tableau de bord capacité vs charge par poste de travail',
    'author': 'Paxo Consulting',
    'depends': ['mrp', 'planning'],
    'data': [
        'security/ir.model.access.csv',
        'views/capacite_charge_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
