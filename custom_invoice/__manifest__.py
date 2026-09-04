# -*- coding: utf-8 -*-
{
    "name": "Custom Invoice Text Block",
    # 1.0.2 : la facture imprimee affiche commercial_id, avec repli sur
    # l'ancienne selection pour les factures anterieures a la bascule.
    "version": "19.0.1.0.3",
    "summary": "Show text block on invoice based on contact boolean field",
    "author": "Your Name",
    "depends": ["account", "custom"],
    "data": [
        "views/report_invoice.xml",
    ],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
