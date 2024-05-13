{
    'name': 'SQLite Connector2',
    'category': '',
    'author': 'Odoo PS',
    'sequence': 358,
    'summary': '',
    'version': '15.0.0.1.2',
    'description': """
        
    """,
    'depends': ['mail'],
    'data': [
        'views/sqlite_connector.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}