# -*- coding: utf-8 -*-
{
    'name': "custom_laquage_report",
    'summary': """
        Custom laquage report""",
    'description': """
        Ce module ajoute un rapport PDF personnalisé pour les commandes d'achat.
    """,
    'author': "My Company",
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'stock', 'purchase'],  # Ajout de 'purchase' comme dépendance

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',  # Si vous avez des règles de sécurité, sinon laissez commenté
        'views/custom_laquage.xml',       # Template QWeb pour le PDF
    ],

    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',  # Vous pouvez également commenter cette ligne si vous n'avez pas de données de démo
    ],

        # Section pour inclure les fichiers statiques
    'assets': {
        'web.assets_backend': [
            'custom_laquage_report/static/src/img/F2M.png', # Chemin vers l'image à inclure
        ],
    },


    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
