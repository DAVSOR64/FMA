{
    "name": "FMA Shop Floor Hide Components",
    "version": "19.0.1.0.1",
    "category": "Manufacturing",
    "summary": "Hide the raw material components and byproducts lists on Shop Floor OF cards.",
    "author": "Paxo Consulting",
    "depends": ["mrp_workorder"],
    "assets": {
        "web.assets_backend": [
            "fma_shopfloor_hide_components/static/src/mrp_display/mrp_display_record_patch.js",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
