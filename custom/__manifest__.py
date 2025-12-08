# -*- coding: utf-8 -*-
{
    "name": "Custom Field Transfer",
    "version": "17.0.1.0.1",
    "summary": "Created and Transfer custom field from contact and sale order to invoice",
    "author": "Your Name",
    "depends": ["base", "sale", "account", "contacts", "sale_stock", "mrp"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_partner_views.xml",
        "views/sale_order_views.xml",
        "views/account_move_views.xml",
        "views/affair_chat_template_views.xml",
        "data/message_templates.xml",
        "data/mail_template_retard.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "custom/static/src/css/custom_styles.css",  # Chemin vers votre fichier CSS
        ],
    },
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
