{
    "name": "Delivery Service Rate",
    "version": "1.1.0",
    "depends": ["stock"],
    "author": "TonNom",
    "category": "Warehouse",
    "summary": "Calcul du taux de service (livraison à temps)",
    "data": [
        "views/delivery_service_rate_view.xml",
        "data/delivery_service_rate_view.sql",
        "views/stock_picking_form_reason.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
