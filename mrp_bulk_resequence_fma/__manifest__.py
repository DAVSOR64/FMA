{
    'name': 'MRP Bulk Resequence FMA',
    'version': '17.0.1.0.6',
    'summary': 'Réordonne les opérations FMA et relance la replanification locale des OF non démarrés',
    'category': 'Manufacturing',
    'author': 'OpenAI',
    'license': 'LGPL-3',
    'depends': ['mrp', 'mrp_replan_workorder'],
    'data': [
        'views/mrp_production_views.xml',
    ],
    'installable': True,
    'application': False,
}
