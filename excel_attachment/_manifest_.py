{
    'name': 'Bon de Livraison Excel',
    'version': '1.0',
    'summary': 'Génère des bons de livraison au format Excel',
    'description': """
    Ce module génère des bons de livraison au format Excel au lieu de PDF.
    """,
    'category': 'Warehouse',
    'author': 'Votre Nom',
    'depends': ['stock'],
    'data': [
        'views/delivery_report_excel_views.xml',  # Votre vue et action serveur
        'security/ir.model.access.csv',  # Les droits d'accès (si nécessaire)
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
