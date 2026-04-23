{
    "name": "FMA KPI Visu Atelier",
    "version": "1.0",
    "author": "PAXO CONSULTING",
    "category": "Manufacturing",
    "summary": "Visu atelier avec retard d'avancement cumulé par poste",
    "description": "Suivi des ordres de travail avec calcul du retard d'avancement et cumul par poste",
    "depends": ["mrp", "fma_mrp_dashboard"],
    "data": [
        "security/ir.model.access.csv",
        "views/mrp_prod_followup_week_views.xml",
        "views/mrp_daily_snapshot_views.xml",
        "views/menu.xml",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}