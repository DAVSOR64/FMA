{
    "name": "FMA Shop Floor — pointage et reperes visuels",
    "version": "19.0.1.3.2",
    "category": "Manufacturing",
    "summary": "Reperes visuels de l'ecran atelier (OT en cours, initiales) et corrections du pointage.",
    "author": "Paxo Consulting",
    "depends": ["mrp_workorder"],
    "assets": {
        "web.assets_backend": [
            "fma_shopfloor_active_css/static/src/scss/shopfloor_active.scss",
            "fma_shopfloor_active_css/static/src/mrp_display/mrp_display_record_patch.js",
            "fma_shopfloor_active_css/static/src/mrp_display/employees_panel_initials.xml",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
