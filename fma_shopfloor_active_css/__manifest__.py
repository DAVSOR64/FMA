{
    "name": "FMA Shop Floor Active Workorder Highlight",
    "version": "17.0.1.0.0",
    "category": "Manufacturing",
    "summary": "Highlight active workorders in Odoo Shop Floor with a visible color indicator.",
    "depends": ["mrp_workorder"],
    "assets": {
        "web.assets_backend": [
            "fma_shopfloor_active_css/static/src/scss/shopfloor_active.scss",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
