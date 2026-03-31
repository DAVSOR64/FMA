# -*- coding: utf-8 -*-
{
    'name': 'Stock Move Quantity Before/After',
    'version': '17.0.1.0.1',
    'category': 'Inventory',
    'summary': 'Affiche la quantité avant et après sur les mouvements de stock',
    'description': """
        Ajoute deux champs sur les lignes de mouvements de stock :
        - Quantité avant le mouvement
        - Quantité après le mouvement

        Le calcul est fait sur l'emplacement pertinent :
        - entrée : emplacement de destination interne
        - sortie : emplacement source interne

        Un assistant permet de recalculer tout l'historique.
    """,
    'author': 'Paxo Consulting',
    'depends': ['stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_move_line_views.xml',
        'wizard/recompute_wizard_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}
