{
    "name": "MRP Bulk Resequence FMA",
    "version": "17.0.1.0.0",
    "summary": "Réordonne en masse les opérations FMA sur les OF non lancés",
    "author": "OpenAI",
    "license": "LGPL-3",
    "depends": ["mrp", "mrp_replan_workorder"],
    "data": [
        "security/ir.model.access.csv",
        "views/mrp_production_views.xml",
        "wizard/mrp_bulk_resequence_wizard_views.xml",
    ],
    "installable": True,
    "application": False,
}
