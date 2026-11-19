{
    "name": "FMA Shop Floor — pointage et reperes visuels",
    "version": "19.0.1.12.0",
    "category": "Manufacturing",
    "summary": "Reperes visuels de l'ecran atelier (OT en cours, initiales) et corrections du pointage.",
    "author": "Paxo Consulting",
    # fma_mrp_ordonnancement porte fma_sale_order_id, l'affaire affichee
    # sur la carte. fma_etiquette_scan sait relier le numero de serie d'une
    # etiquette a l'ordre qui la fabrique — c'est lui qui porte la table de
    # retour AZERTY et le QR code.
    "depends": [
        "mrp_workorder", "fma_mrp_ordonnancement", "fma_etiquette_scan"],
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
