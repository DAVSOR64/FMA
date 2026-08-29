# -*- coding: utf-8 -*-
{
    "name": "Custom Invoice Text Block",
    # 1.0.2 : remise en service du gabarit apres la migration v19 — xpath
    # reancre sur #payment_term, vues reactivees, blocs standard masques au lieu
    # d'etre supprimes, SIRET via company_registry, titre sous le pave adresse.
    # 1.0.3 : la TVA societe quitte l'entete repete et revient dans le corps,
    # donc sur la seule premiere page, comme en v17.
    "version": "19.0.1.0.3",
    "summary": "Show text block on invoice based on contact boolean field",
    "author": "Your Name",
    "depends": ["account", "custom", "web"],
    "data": [
        "views/report_invoice.xml",
    ],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
