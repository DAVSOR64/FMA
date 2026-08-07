# -*- coding: utf-8 -*-
{
    "name": "FMA Import Pricer",
    # 1.1.0 : mise en lot depuis le pricer. Ajoute des colonnes
    # (product_template.pricer_signature, fma_lot_fabrication.pricer_lot_key,
    # create_lots sur le wizard) : la version DOIT etre incrementee, sinon
    # Odoo.sh deploie le code sans jouer la mise a jour et le registre
    # reference des colonnes inexistantes.
    # 1.2.0 : un article ou une ligne introuvable n'interrompt plus l'import ;
    # le manque est inscrit sur le lot (nouvelles colonnes import_issues /
    # import_incomplete), qui reste bloque a la confirmation.
    # 1.3.0 : chaque menuiserie devient un article fabrique MTO avec sa propre
    # nomenclature (1 sous-ensemble debite + quincaillerie + vitrage), au lieu
    # de l'unique nomenclature de projet posee par sqlite_connector.
    # 1.4.0 : mesure du debit sur le lot (besoin en metres face aux barres
    # achetees, chute par reference) — nouvelles colonnes sur le lot et sur
    # la ligne de besoin matiere.
    # 1.5.0 : gamme d'operations sur la nomenclature de chaque menuiserie, et
    # rattachement du vitrage sur la position de base (il disparaissait de la
    # nomenclature des le deuxieme lot importe).
    # 1.6.0 : la nomenclature n'est plus reconstruite quand l'empreinte n'a
    # pas change ni quand un composant reste introuvable ; le temps de debit
    # part sur le sous-ensemble debite.
    "version": "19.0.1.6.0",
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
        # Porte les lots de fabrication, leur affectation par ligne de devis
        # et leur besoin matiere, que l'import alimente depuis le pricer.
        "fma_lot_fabrication",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizard/fma_pricer_import_wizard_views.xml",
        "views/sale_order_views.xml",
        "views/fma_lot_fabrication_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
