{
    "name": "SO Coût MOD réel Odoo",
    "version": "17.0.1.0.0",
    "category": "Manufacturing/Sales",
    "summary": "Calcule le coût MOD réel sur le devis/commande via les temps opérateurs des OF liés au projet",
    "author": "FMA/JBS",
    "license": "LGPL-3",
    "depends": ["sale_management", "mrp_workorder", "hr"],
    "data": [
        "views/sale_order_views.xml"
    ],
    "installable": True,
    "application": False,
}
