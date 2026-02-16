{
    'name': "Replan WorkOrder",
    'version': "17.0.0.0.1",
    "license": "LGPL-3",
    'category': 'Manufacturing',
    'summary': 'Planification atelier avec règle 1 opération/jour par OF',
    'description': """
        Planification intelligente des ordres de fabrication :
        - 1 opération par jour par OF
        - Prise en compte des calendriers (jours fériés, week-ends)
        - Planification à rebours depuis date de livraison
        - Déclenchement automatique à la validation de commande
    """,
    'author': 'Paxo Consulting',
    'website': 'https://www.paxoconsulting.com',
    'depends': [
        'mrp',
        'sale_mrp',
        'resource',
    ],
    
    'data': [
        'views/sale_order_views.xml',
        'views/mrp_workorder_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
