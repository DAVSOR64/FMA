# -*- coding: utf-8 -*-
{
    "name": "FMA Lots de fabrication",
    "version": "19.0.1.0.0",
    "category": "Manufacturing",
    "summary": "Mise en lot des menuiseries : commerce (devis) -> production (OF debit + OF assemblage)",
    "description": """
Lots de fabrication FMA
=======================

Relie la partie commerciale (lignes de devis = menuiseries) a la partie
production (ordres de fabrication) via une notion de **lot de fabrication**.

Principes
---------
* Une ligne de devis = une menuiserie (ou N menuiseries identiques).
* Un lot regroupe des lignes de devis, **avec une quantite par ligne**
  (une ligne de 5 menuiseries peut etre repartie sur 2 lots).
* Le lotissement est realise **dans Odoo**, par un wizard lance depuis le
  devis : on saisit un numero de lot et une quantite en face de chaque ligne.
* Un lot genere, sur bouton :
    - 1 **OF Debit** (niveau lot) qui porte l'optimisation de coupe et les appros ;
    - N **OF Assemblage** (1 par menuiserie) ou l'on declare la fabrication.
* Les deux niveaux d'OF sont relies par la reference de lot, sans dependre du
  parent/enfant natif Odoo.
* Traçabilite matiere : l'OF Debit produit un article intermediaire
  "Ensemble debite" que chaque OF Assemblage consomme.

Voir README.md pour le detail du parametrage.
""",
    "author": "FMA",
    "license": "LGPL-3",
    "depends": [
        "base",
        "mail",
        "sale",
        "sale_stock",
        "stock",
        "mrp",
        "purchase",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/fma_lot_security.xml",
        "data/ir_sequence.xml",
        "data/product_data.xml",
        "views/fma_lot_fabrication_views.xml",
        "views/sale_order_views.xml",
        "views/mrp_production_views.xml",
        "views/purchase_order_views.xml",
        "views/res_config_settings_views.xml",
        "wizard/fma_lot_wizard_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
