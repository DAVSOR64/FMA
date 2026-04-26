{
    "name": "FMA KPI Visu Atelier",
    "version": "1.1.0",
    "author": "PAXO CONSULTING",
    "category": "Manufacturing",
    "summary": "Suivi prod : charge vs capacité et visu atelier",
    "description": "Vue métier de suivi production hebdomadaire connectée au recalcul capacité/charge.",
    "depends": ["mrp", "fma_mrp_dashboard"],
    "data": [
        "security/ir.model.access.csv",
        "views/mrp_prod_followup_week_views.xml",
        "views/mrp_daily_snapshot_views.xml",
        "views/menu.xml"
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
