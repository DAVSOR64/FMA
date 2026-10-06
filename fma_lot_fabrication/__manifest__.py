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
    # 1.49.0 : le besoin matiere ne s'imprime qu'apres generation des OF,
    # les casiers portent leur numero de serie, et une liste par article
    # rejoint le document pour la prise en rayon.
    # 1.50.0 : le detail par casier devient un detail par article, avec
    # le casier servi sur chaque ligne. Meme contenu, un passage en
    # rayon par article au lieu d'un par casier.
    # 1.51.0 : le detail du besoin matiere ne porte que la quincaillerie.
    # 1.52.0 : la liste de quincaillerie porte l'emplacement de stock en
    # premiere colonne et suit l'ordre des rayons ; l'unite disparait.
    # 1.53.0 : l'emplacement est cherche sous STOCK seulement, jamais en
    # pre-fabrication, et c'est le premier de la tournee qui est retenu.
    # 1.54.0 : le document devient « Liste de quincaillerie » : profiles et
    # vitrages quittent aussi le recapitulatif, le repere se reduit a la
    # position et l'emplacement au nom court.
    # 1.56.0 : la liste de quincaillerie se fie au CLASSEMENT de l'article —
    # categorie, famille, sous-famille : profiles (complementaires compris),
    # vitrages et panneaux ecartes, le reste est de la quincaillerie — et non
    # plus a la table LOGIKAL d'origine, qui ne sert plus que pour l'article
    # que rien ne range. Aucun champ ni valeur ajoutes. Elle lit les
    # composants reels des ordres d'assemblage des qu'ils existent, et un
    # composant ajoute sur un ordre rejoint le bon de sortie du lot.
    # 1.57.0 : libelle du bouton « Replanifier depuis le débit » — il
    # annoncait que les achats suivaient, ce que le code ne fait pas, a
    # dessein. Vue seule : sans montee de version elle n'est pas rejouee.
    # 1.60.0 : l'OF de debit porte l'article « Debit du lot », pour le
    # nombre de menuiseries du lot, et non plus l'ensemble debite du premier
    # repere pour sa seule quantite — un lot de 10 affichait « 8 ». Tous les
    # ensembles debites sortent en sous-produits, et se partagent le cout de
    # l'ordre au prorata de leurs metres de profile. « Debit du lot » n'est
    # plus suivi en stock (migration). Les ordres deja generes ne sont pas
    # repris : les deux formes cohabitent.
    # 1.61.0 : le type de fabrication du debit se choisit sur le PREFIXE
    # de sequence de l'entrepot, et non plus sur manu_type_id, qui peut
    # designer un type numerotant pour un autre atelier.
    # 1.62.0 : colonne Lot et regroupements projet / lot sur
    # l'ordonnancement ; la replanification dit quand elle ne decale rien.
    "version": "19.0.1.64.0",
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
