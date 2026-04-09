{
    "name": "MRP FMA Replan Custom Finish",
    "version": "17.0.1.0.0",
    "summary": "Replanification OF/OT à partir de la date custom de fin",
    "depends": ["mrp", "purchase", "mail", "mrp_replan_workorder"],
    "data": [
        "security/ir.model.access.csv",
        "views/mrp_production_views.xml",
        "wizards/mrp_recalc_planif_wizard_views.xml"
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3"
}
