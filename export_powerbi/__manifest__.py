{
    "name": "Export PowerBI",
    "author": "Paxo Consulting",
    "version": "19.0.1.1.3",
    
    "summary": "Export clients, commandes, factures vers SFTP pour Power BI",
    "depends": ["base", "sale", "account", "purchase", "stock", "mrp", "custom"],
    "data": [
        "data/ir_cron.xml",
        "views/export_config_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
}
