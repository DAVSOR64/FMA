# -*- coding: utf-8 -*-
{
    "name": "Custom Delivery",
    "summary": "Custom delivery slip and picking colisage fields",
    "description": "Adds colisage and palette information on stock pickings and customizes the delivery report.",
    "author": "Odoo PS",
    "website": "http://www.yourcompany.com",
    "category": "Inventory/Delivery",
    "version": "19.0.1.0.1",
    "license": "LGPL-3",
    "depends": ["base", "stock", "sale_stock", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "views/stock.picking.xml",
        "views/delivery.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "custom_delivery/static/src/img/lieu.png",
            "custom_delivery/static/src/img/camion.png",
            "custom_delivery/static/src/img/appel-telephonique.png",
            "custom_delivery/static/src/img/enveloppe.png",
        ],
    },
    "installable": True,
    "application": False,
}
