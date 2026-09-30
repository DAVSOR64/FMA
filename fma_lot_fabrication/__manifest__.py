# -*- coding: utf-8 -*-
{
    "name": "FMA Lots de fabrication",
    # 1.0.1 : _compute_product_uom_id de fma.lot.material.line n'affectait pas
    # de valeur quand l'article etait absent, laissant un champ requis vide.
    # 1.0.2 : retrait du bouton « Mise en lot » du devis, les lots etant
    # desormais crees par l'import du pricer.
    # 1.0.3 : l'OF de debit consomme le besoin matiere meme quand l'article
    # debite porte une nomenclature sans composant (gamme de debit seule).
    # 1.1.0 : les OF d'assemblage ne sont plus crees par le lot mais par
    # l'approvisionnement standard a la confirmation de la commande ; le lot
    # les scinde selon sa repartition et se les rattache. Le bouton du lot ne
    # cree plus que l'OF de debit, et complete les assemblages manquants.
    # 1.39.0 : replanifier l'OF de debit entraine les assemblages, et la
    # date de livraison est controlee SUR EUX. Les bons d'achat ne sont
    # plus deplaces : c'est une negociation fournisseur, pas une
    # consequence du planning atelier.
    # 1.40.0 : la date projetee des assemblages tient compte du report
    # derriere la fin du debit, et non du seul decalage. Un decalage nul
    # donnait une projection nulle : des assemblages annonces AVANT le
    # debit qui les alimente, et declares a l'heure.
    # 1.41.0 : le type dans le lot (Debit / Assemblage) devient une
    # colonne et deux filtres sur l'ecran d'ordonnancement.
    # 1.42.0 : l'etiquette est lue sur tag_ids, le champ standard ;
    # plafond a 8 menuiseries ; la designation du lot porte l'affaire et
    # le rang du lot ; la quantite commandee quitte la vue du lot.
    # 1.43.0 : la designation du lot porte le rang du lot dans la
    # commande — « A26-00-00002 - Lot 3 » — et non plus le nom de la
    # phase LOGIKAL.
    # 1.44.0 : le titre du formulaire porte la designation du lot, le
    # numero de sequence passant en sous-titre.
    # 1.45.0 : dans l'entrepot que l'etiquette designe, le debit prend le
    # type d'operation des assemblages plutot que le manu_type_id de
    # l'entrepot, qui pointait un autre atelier.
    # 1.46.0 : « Date planifiee » du lot porte le debut de son OF de
    # debit, et suit donc les replanifications. Reprise des lots deja en
    # base en post-migrate.
    # 1.47.0 : « Generer les OF » scinde les assemblages en un ordre par
    # menuiserie et pose son numero de serie. Le magasin prepare des
    # casiers deja numerotes, l'atelier declare une menuiserie a la fois.
    # 1.48.0 : la feuille de besoin matiere nomme le lot comme l'ecran.
    "version": "19.0.1.48.0",
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
        # La vue OF en deux colonnes rassemble des champs de ces trois
        # modules : niveau de complexite et date de fin (custom), atelier
        # (fma_atelier), fin macro forcee (mrp_capacity_planning).
        "custom",
        "fma_atelier",
        "mrp_capacity_planning",
        # Porte l'ecran d'ordonnancement que la vue ci-dessous etend.
        "fma_mrp_ordonnancement",
        "base",
        "mail",
        "sale",
        "sale_stock",
        "stock",
        "mrp",
        "purchase",
        # purchase_stock porte purchase.order.line.move_dest_ids, qui relie
        # un achat a l'OF (et donc au lot) qui l'a declenche.
        "purchase_stock",
    ],
    "data": [
        "views/mrp_production_ordonnancement_views.xml",
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
        "report/fma_lot_sortie_matiere.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
