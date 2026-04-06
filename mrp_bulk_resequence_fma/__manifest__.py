{
    'name': 'MRP Bulk Resequence FMA',
    'version': '17.0.1.0.1',
    'summary': 'Réordonne en masse les opérations FMA puis replanifie localement les OF',
    'category': 'Manufacturing',
    'author': 'OpenAI',
    'license': 'LGPL-3',
    'depends': ['mrp'],
    'data': [
        'views/mrp_production_views.xml',
    ],
    'installable': True,
    'application': False,
}
