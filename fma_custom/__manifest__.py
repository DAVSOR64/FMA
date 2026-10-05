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
    # 1.0.21 : rattachement d'un achat a une commande client (champ
    # « Commande client » sur l'achat et ses lignes), prix de revient ventile
    # par ligne de commande, achats du projet non rattaches signales. Champs
    # stockes nouveaux : la mise a jour du module est obligatoire.
    # 1.0.22 : les achats de services rattaches (sous-traitance, laquage,
    # pose) entrent au PRI, dans la matiere, et sont affiches a part ; MOD
    # saisie et MOD calculee par Odoo cote a cote, avec leur ecart.
    "version": "19.0.1.0.24",
    "depends": ["custom", "hr", "sale", "purchase", "mrp", "account", "stock"],
    "data": [
        "views/mail_templates.xml",
        "views/sale_order_actions.xml",
        "views/sale_order_views.xml",
        "views/purchase_order_views.xml",
        "views/res_partner_actions.xml",
        "views/hr_employee_actions.xml",
        "views/stock_picking_actions.xml",
        "views/stock_picking_views.xml",
        "data/ir_cron.xml",
    ],
    "post_init_hook": "post_init_hook",
    "license": "LGPL-3",
}
