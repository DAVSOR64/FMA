# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "FMA: Custom",
    "description": """
        Custom module delete button on email.
        Also carries business rules migrated from Odoo Studio automations
        and server actions (sale.order, purchase.order, mrp.production,
        account.move, res.partner, stock.picking) -- see STUDIO_AUDIT.md at
        the repo root for the full inventory and rationale.
    """,
    "summary": "Custom delete button",
    "author": "Odoo PS",
    "version": "19.0.1.0.3",
    "depends": ["custom", "hr", "sale", "purchase", "mrp", "account", "stock"],
    "data": [
        "views/mail_templates.xml",
        "views/sale_order_actions.xml",
        "views/res_partner_actions.xml",
        "views/stock_picking_actions.xml",
        "data/ir_cron.xml",
    ],
    "post_init_hook": "post_init_hook",
    "license": "LGPL-3",
}
