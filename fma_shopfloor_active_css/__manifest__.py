{
    "name": "FMA Shop Floor — pointage et reperes visuels",
    "version": "19.0.1.4.3",
    "category": "Manufacturing",
    "summary": "Reperes visuels de l'ecran atelier (OT en cours, initiales) et corrections du pointage.",
    "author": "Paxo Consulting",
    # fma_mrp_ordonnancement porte fma_sale_order_id, l'affaire affichee
    # sur la carte.
    "depends": ["mrp_workorder", "fma_mrp_ordonnancement"],
    "assets": {
        "web.assets_backend": [
            "fma_shopfloor_active_css/static/src/scss/shopfloor_active.scss",
            "fma_shopfloor_active_css/static/src/mrp_display/mrp_display_record_patch.js",
            "fma_shopfloor_active_css/static/src/mrp_display/employees_panel_initials.xml",
            "fma_shopfloor_active_css/static/src/mrp_display/mrp_display_record_affaire.xml",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
