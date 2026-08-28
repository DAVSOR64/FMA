# -*- coding: utf-8 -*-
{
    "name": "Custom Invoice Text Block",
    # 1.0.2 : la facture imprimee affiche commercial_id, avec repli sur
    # l'ancienne selection pour les factures anterieures a la bascule.
    # 1.0.3 : xpath du bloc affacturage reancre sur #payment_term, dont la
    # classe a change en v19 et qui desactivait toute la vue heritee.
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
