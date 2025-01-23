# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': "custom_purchase_documents",
    'summary': """
        Custom purchase documents""",
    'description': """
        Ce module ajoute des rapports PDF personnalisés pour les commandes d'achat.
    """,
    'author': "Odoo PS",
    'version': '17.0.1.0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'stock', 'purchase'],  # Ajout de 'purchase' comme dépendance

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',  # Si vous avez des règles de sécurité, sinon laissez commenté
        # 'views/custom_laquage.xml',       # Template QWeb pour le PDF
        # 'views/custom_invoice_filling.xml',
        # 'views/custom_invoice.xml',
    ],

    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',  # Vous pouvez également commenter cette ligne si vous n'avez pas de données de démo
    ],

        # Section pour inclure les fichiers statiques
    'assets': {
        'web.assets_backend': [
            'custom_purchase_documents/static/src/img/F2M.png', # Chemin vers l'image à inclure
        ],
    },


    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
