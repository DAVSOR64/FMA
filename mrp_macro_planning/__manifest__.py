# -*- coding: utf-8 -*-
{
    'name': 'MRP Macro Planning - Capacité vs Charge',
    'version': '17.0.3.0.0',
    'category': 'Manufacturing',
    'summary': 'Tableau de bord capacité vs charge par poste de travail et par opérateur avec répartition calendaire',
    'author': 'Paxo Consulting',
    'depends': ['mrp', 'planning', 'hr'],
    'data': [
        'security/ir.model.access.csv',
        'views/capacite_charge_views.xml',
        'views/capacite_operateur_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
