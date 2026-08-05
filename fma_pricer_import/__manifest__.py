# -*- coding: utf-8 -*-
{
    "name": "FMA Import Pricer",
    "version": "19.0.1.0.0",
    "category": "Sales",
    "summary": "Importer un chiffrage LOGIKAL / Pricer directement depuis un devis",
    "description": """
Import Pricer depuis le devis
=============================

Inverse le sens de l'import LOGIKAL.

**Avant** : on creait un devis dont le *nom* devait reproduire exactement le
nom du projet LOGIKAL, puis on lancait l'export depuis le menu SQLite
Connector, qui retrouvait le devis par ce nom.

**Maintenant** : on cree l'entete du devis normalement dans Odoo (numero
genere par Odoo, bon client), puis on clique sur **Import Pricer** et on
depose le fichier. L'import ecrit dans ce devis-la ; le client et la date
saisis dans Odoo ne sont plus ecrases.

Le module ``sqlite_connector`` reste en place : chaque import y cree un
enregistrement, avec ses logs, pour consultation.
""",
    "author": "FMA",
    "license": "LGPL-3",
    "depends": [
        "sale",
        "sqlite_connector",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizard/fma_pricer_import_wizard_views.xml",
        "views/sale_order_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
