{
    'name': 'expfrs',
    'summary': """Export des commandes fournisseurs en XML""",
    'description': """Module permattant d exporter les commandes fournisseurs en XML""",
    'author': "DAVSOR",
    'category': 'Uncategorized',
    'version': '15.0.0.1.1',
    'depends': ['base'],

    'data': [
        'security/ir.model.access.csv',
        'views/fournisseurs.xml',
        'views/templates.xml',
        'views/views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
