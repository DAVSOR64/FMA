{
    'name': 'Delivery Service Rate',
    'version': '1.0',
    'depends': ['stock'],
    'author': 'AleBor',
    'category': 'Warehouse',
    'summary': 'Calcul du taux de service (livraison à temps)',
    'data': [
        'views/delivery_service_rate_view.xml',
        'data/delivery_service_rate_view.sql',
    ],
    'installable': True,
    'application': False,
}
