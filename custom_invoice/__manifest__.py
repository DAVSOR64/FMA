# -*- coding: utf-8 -*-
{
    "name": "Custom Invoice Text Block",
    # 1.0.2 : remise en service du gabarit apres la migration v19 — xpath
    # reancre sur #payment_term, vues reactivees, blocs standard masques au lieu
    # d'etre supprimes, SIRET via company_registry, titre sous le pave adresse.
    "version": "19.0.1.0.2",
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
