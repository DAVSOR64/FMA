from odoo import api, SUPERUSER_ID

# safe_eval does not expose getattr/hasattr — use direct field access instead.
# analytic_distribution is always present on sale.order.line in v19.
_NEW_CODE = """\
for po in records:
    if po.sale_order_count:
        sale_order = po._get_sale_orders()[:1]
        if sale_order:
            analytic_dist = {}
            for sol in sale_order.order_line:
                if sol.analytic_distribution:
                    analytic_dist = sol.analytic_distribution
                    break
            if analytic_dist:
                for pol in po.order_line:
                    pol['analytic_distribution'] = analytic_dist
"""


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    actions = env['ir.actions.server'].search([
        ('model_id.model', '=', 'purchase.order'),
        ('code', 'ilike', 'analytic_distribution'),
    ])
    for action in actions:
        action.write({'code': _NEW_CODE})
        cr.execute(
            "INSERT INTO ir_logging"
            " (name, type, level, message, path, line, func, dbname, create_date)"
            " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(), now())",
            ('purchase_order_export',
             f"Migration 19.0.0.6.0: fixed safe_eval-compatible code in action '{action.name}' (id={action.id})",
             __file__, '0', 'migrate'),
        )
