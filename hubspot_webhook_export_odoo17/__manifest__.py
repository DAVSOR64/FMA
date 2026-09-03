{
    "name": "Export HubSpot Webhook FMA-F2M",
    "version": "19.0.1.1.3",
    "category": "Sales/CRM",
    "summary": "Export quotidien des entreprises, devis et commandes Odoo vers un webhook n8n/HubSpot",
    "author": "JBS / David Soria",
    "license": "LGPL-3",
    "depends": ["base", "sale_management", "contacts"],
    "data": [
        "security/ir.model.access.csv",
        "views/hubspot_actions.xml",
        "data/ir_cron.xml",
        "views/res_config_settings_views.xml",
        "views/hubspot_export_log_views.xml"
    ],
    "installable": True,
    "application": False,
}
