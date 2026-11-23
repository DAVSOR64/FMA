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
    # 1.7.0 : « Import Pricer » quitte la barre d'etat pour le menu Action.
    # 1.14.0 : le pivot accueille les commandes fournisseur (Purchase /
    # OrderLine) et un adaptateur lit l'export de commande TechDesign. Ce
    # fichier ne porte ni menuiserie, ni position, ni coupe : il ne cree pas
    # de devis, il complete un lot avec le besoin d'achat reel.
    # 1.15.0 : adaptateur du chiffrage TechDesign (JobExport) et aiguillage
    # du wizard sur le format reel du fichier. Les deux pricers passent
    # desormais par le meme wizard : LOGIKAL en SQLite, TechDesign en XML.
    # 1.16.0 : le wizard n'appelle le connecteur SQLite que pour un export
    # LOGIKAL. Sur un XML TechDesign, le pivot est l'import a lui seul.
    # 1.17.0 : le moteur cree lui-meme articles et lignes de devis pour les
    # pricers sans redacteur. TechDesign n'a pas d'equivalent de
    # sqlite_connector : sans cela le devis restait vide et les lots orphelins.
    # 1.18.0 : la reference LOGIKAL des articles est lue dans le numero SAP du
    # chiffrage TechDesign. Les deux pricers designent enfin le meme article de
    # la meme facon, condition pour rapprocher sans creer de doublon.
    # 1.19.0 : creation des articles et vitrages manquants pour les pricers
    # sans redacteur, a la convention et aux routes de sqlite_connector, et
    # normalisation des libelles d'operations de TechDesign.
    # 1.37.0 : l'OF de debit ne garde que l'operation Debit. L'usinage sur
    # banc (CU) se fait sur des barres deja coupees mais appartient a la
    # menuiserie -- c'est elle qu'on usine, pas le lot : il part sur l'OF
    # d'assemblage, avec le reste de la gamme.
    # 1.38.0 : les articles libres sont crees a l'import, sur le
    # fournisseur « NON DEF » et rattaches a l'affaire ; une activite
    # previent celui qui a depose le fichier de ce qui reste a traiter.
    # 1.39.0 : l'import reste possible sur un devis VALIDE. La validation
    # est une etape interne, pas une vente ; seule la confirmation ferme
    # la porte.
    # 1.40.0 : la recherche d'article applique la regle de reference de
    # sqlite_connector — code de BASE prefixe par fournisseur — au lieu de
    # chercher le code brut du fichier, qui n'est jamais ce qui est ecrit.
    # 1.41.0 : le fournisseur du CODE remonte du fichier, et la regle de
    # reference le reconnait meme sous un libelle approchant.
    # 1.42.0 : la teinte des profiles suit l'exception F2M du connecteur —
    # chez F2M les profiles sont crees sans teinte.
    # 1.43.0 : l'article d'une menuiserie prend le nom de sa ligne de
    # commande, et le garde a jour tant que personne ne le renomme ; les
    # semi-finis se nomment « Débit – ... » et « Quincaillerie – ... », et
    # leurs nomenclatures recoivent une reference. Reprise de l'existant en
    # post-migrate (sqlite_connector/noms_articles.py).
    # 1.53.0 : les temps de main d'oeuvre se lisent avec la table du SITE.
    # LOGIKAL donne le meme TimeType a des travaux differents d'un atelier a
    # l'autre : le 11 est du montage chez FMA, du remontage chez F2M, et le
    # 10 — vitrage chez FMA — est du remontage chez F2M, ou le vitrage ne se
    # pose pas en atelier.
    # 1.56.0 : les unites viennent du FICHIER et non plus d'une deduction.
    # AllProfiles.Units_Unit vaut « m » sur les 111 profiles des dix-huit
    # exports releves, Articles.Units_Unit departe « pce » et « m » article
    # par article, et chaque longueur se lit avec son unite d'affichage au
    # lieu d'etre supposee en millimetres. Le besoin de debit s'ecrit donc
    # toujours en METRES — la meme grandeur que le besoin matiere du lot — et
    # le repli en fraction de barre disparait : une unite qu'on ne sait pas
    # rapporter au metre fait remonter un manque qui NOMME l'article.
    # 1.57.0 : le detail des coupes survit a l'import. Une nomenclature dit
    # un besoin cumule — « 11,076 m de T591007 » — et c'est inutilisable a la
    # scie : il faut savoir que ce sont huit coupes, de 2,092 m a 0,316 m. Le
    # fichier le disait, le cumul par (reference, teinte) le perdait. Nouveau
    # modele fma.lot.cut.line, en lecture seule, lu des deux bouts : onglet
    # « Coupes » sur le lot a cote du besoin matiere, et sur la fiche de
    # l'ensemble debite a cote de sa nomenclature.
    # 1.58.0 : « ML » est reconnue comme unite de longueur. Le releve du
    # 23/11/2026 a montre que c'est une unite de REFERENCE dans la base --
    # 2 827 articles, 46 unites de barre rattachees, 63 816 mouvements de
    # stock -- qu'Odoo ne sait pas convertir vers son metre standard, et que
    # la demonstration par la longueur de barre ne pouvait pas sauver : une
    # unite de reference n'a aucun rattachement a mesurer. La version
    # precedente bloquait donc l'unite la plus employee de la maison. Un
    # metre lineaire EST un metre ; la liste UNITES_LONGUEUR, deja tenue a la
    # main pour lire le fichier, sert desormais aussi a reconnaitre l'unite
    # de reference cote Odoo. Au passage, un rapport de rattachement de 1 ne
    # vaut plus demonstration : « Piece » vaut 1 « Unites » et un profile
    # ordinaire se conditionne au metre, de quoi se prouver tout seul.
    "version": "19.0.1.58.0",
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
        "views/mrp_workcenter_views.xml",
        "views/fma_lot_fabrication_views.xml",
        "views/product_template_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
