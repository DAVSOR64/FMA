{
    "name": "Export HubSpot Webhook FMA-F2M",
    "version": "17.0.1.0.0",
    "category": "Sales/CRM",
    "summary": "Export quotidien des clients et chiffrages Odoo vers un webhook n8n/HubSpot",
    "author": "JBS / David Soria",
    "license": "LGPL-3",
    "depends": ["base", "sale_management", "contacts"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/res_config_settings_views.xml",
        "views/hubspot_export_log_views.xml"
    ],
    "installable": True,
    "application": False,
}
