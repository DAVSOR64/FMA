{
    "name": "FMA Shop Floor — pointage et reperes visuels",
    "version": "19.0.1.14.0",
    "category": "Manufacturing",
    "summary": "Reperes visuels de l'ecran atelier (OT en cours, initiales) et corrections du pointage.",
    "author": "Paxo Consulting",
    # fma_mrp_ordonnancement porte fma_sale_order_id, l'affaire affichee
    # sur la carte.
    #
    # fma_etiquette_scan N'EST PAS UNE DEPENDANCE, bien que ce module appelle
    # sa methode fma_ordre_du_code pour traduire un numero de serie en numero
    # d'ordre. Deux raisons, et la premiere coute cher :
    #
    # 1. une staging RESTAURE LA PRODUCTION. Declarer la dependance oblige la
    #    mise a jour a installer fma_etiquette_scan — avec ses vues, ses
    #    donnees et sa propre dependance helpdesk — en plein build, sur une
    #    base ou il ne l'etait peut-etre pas. Un module d'affichage ne doit
    #    pas pouvoir faire tomber un deploiement pour un confort de scan ;
    # 2. l'appel est deja ENVELOPPE dans un try/catch cote navigateur : sans
    #    le module, le scan retombe exactement sur son comportement
    #    d'origine. La dependance n'apporte donc aucune garantie que le code
    #    ne se donne pas lui-meme.
    "depends": ["mrp_workorder", "fma_mrp_ordonnancement"],
    "assets": {
        "web.assets_backend": [
            "fma_shopfloor_active_css/static/src/scss/shopfloor_active.scss",
            "fma_shopfloor_active_css/static/src/mrp_display/mrp_display_record_patch.js",
            "fma_shopfloor_active_css/static/src/mrp_display/mrp_display_barcode_of.js",
            "fma_shopfloor_active_css/static/src/mrp_display/mrp_display_mes_ordres.js",
            "fma_shopfloor_active_css/static/src/mrp_display/employees_panel_initials.xml",
            "fma_shopfloor_active_css/static/src/mrp_display/mrp_display_record_affaire.xml",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
