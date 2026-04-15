{
    'name': "Replan WorkOrder",
    'version': "17.0.1.1.0",
    'license': "LGPL-3",
    'category': 'Manufacturing',
    'summary': 'Planification atelier : macro planning, recalcul différé, bouton Replanifier',
    'description': """
        Planification intelligente des ordres de fabrication :
        - 1 opération par jour par OF (rétroplanning depuis date livraison)
        - Recalcul DIFFÉRÉ : bouton « Replanifier » + cron 3×/jour (8h / 12h / 18h)
          → supprime le blocage de 30 s–1 min à l'enregistrement
        - « Tous fabriquer » : validation automatique des transferts produit fini
        - Vue liste Planning OF avec bouton Replanifier
    """,
    'author': 'Paxo Consulting',
    'website': 'https://www.paxoconsulting.com',
    'depends': [
        'mrp',
        'sale_mrp',
        'resource',
    ],
    'data': [
        'data/mrp_replan_cron.xml',
        'views/sale_order_views.xml',
        'views/mrp_workorder_views.xml',
        'views/mrp_production_planning_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
