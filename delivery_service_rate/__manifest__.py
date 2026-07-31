{
    "name": "Delivery Service Rate",
    "version": "19.0.1.1.0",
    "author": "Paxo Consulting",
    "category": "Warehouse",
    "summary": "Calcul du taux de service (livraison à temps)",
    "license": "LGPL-3",
    "depends": ["stock", "sale_management"],
    "data": [
        "views/delivery_service_rate_view.xml",
        "views/stock_picking_form_reason.xml",
    ],
    "installable": True,
    "application": False,
}
