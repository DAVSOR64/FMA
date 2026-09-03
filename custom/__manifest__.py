# -*- coding: utf-8 -*-
{
    "name": "Custom Field Transfer",
    # 1.0.31 : reorganisation de la fiche devis (handoff ergonomie) :
    # frise de chronologie en lecture seule en haut, onglets « Livraison &
    # acces » et « Chronologie », horaires en float_time, libelles colores
    # retires.
    # 1.0.33 : un numero de version ne doit jamais reculer. Le commit casse
    # etait en .32 ; revenir a .31 a fait passer trois commits de vue sans
    # que la mise a jour soit rejouee. On repart au-dessus de .32.
    # 1.0.36 : champ Commercial unique (Many2one hr.employee) sur devis et
    # facture, recopie du client puis fige. Filtre sur le departement Commerce.
    # 1.0.54 : integration de main. Le module y gagne le groupe « Suivi
    # commercial » sur la fiche contact ; sans changement de version la mise
    # a jour ne serait pas rejouee, la branche etant deja au-dessus de .34.
    # 1.0.55 : remontees V19 cote vues — intitules des champs variante
    # (residu Studio en base), onglet Vitrage sur la fiche « edition
    # rapide » ouverte depuis un achat, repere avant le produit sur la
    # ligne d'achat. Sans montee de version la mise a jour n'est pas
    # rejouee et aucune vue ne bouge.
    # 1.0.56 : la date de debut de l'OF passe en lecture seule sur le
    # formulaire standard — elle est posee par l'ordonnancement, une
    # saisie manuelle desalignait l'OF de son planning.
        # 1.0.57 : la colonne Repere de la ligne d'achat suit la meme regle
    # que le PDF (x_studio_posit sinon x_studio_position) ; elle restait
    # vide alors que le PDF portait bien un repere.
    "version": "19.0.1.0.63",
    "summary": "Created and Transfer custom field from contact and sale order to invoice",
    "author": "Your Name",
    "depends": [
        "base", "sale", "account", "contacts", "sale_stock", "mrp", "hr",
        "fma_studio_models", "project", "purchase", "purchase_requisition", "helpdesk",
        "stock_barcode",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/res_partner_views.xml",
        "views/sale_order_views.xml",
        "views/account_move_views.xml",
        "views/affair_chat_template_views.xml",
        "views/sale_delay_reason_views.xml",
        "views/stock_picking_views.xml",
        "views/mrp_production_views.xml",
        "views/purchase_order_views.xml",
        "views/product_views.xml",
        "data/message_templates.xml",
    ],
    # Une seule cle "assets" : il y en avait deux, et la seconde ecrasait
    # silencieusement la premiere (dictionnaire Python). static/src/css/
    # custom_styles.css n'etait donc plus charge depuis longtemps -- il colore
    # les libelles de dates du devis, retires volontairement en 1.0.31 : il
    # reste hors bundle, a supprimer si plus personne n'en veut.
    "assets": {
        "web.assets_backend": [
            "custom/static/src/fma_timeline/fma_timeline.js",
            "custom/static/src/fma_timeline/fma_timeline.xml",
            "custom/static/src/fma_timeline/fma_timeline.scss",
            "custom/static/src/purchase_order_line/product_and_description_o2m.js",
        ],
    },
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
