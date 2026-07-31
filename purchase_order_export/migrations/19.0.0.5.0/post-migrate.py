from odoo import api, SUPERUSER_ID

# sale.order.analytic_account_id was removed in v19.
# In v19, analytics live on order lines via analytic_distribution (dict).
_NEW_CODE = """\
for po in records:
    if po.sale_order_count:
        sale_order = po._get_sale_orders()[:1]
        if sale_order:
            analytic_dist = {}
            for sol in sale_order.order_line:
                if getattr(sol, 'analytic_distribution', None):
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
        ('code', 'ilike', 'analytic_account_id'),
    ])
    for action in actions:
        action.write({'code': _NEW_CODE})
        automations = env['base.automation'].search([
            ('action_server_ids', 'in', action.ids),
        ])
        _logger_msg = "Migration 19.0.0.5.0: patched automated action '%s' (id=%s)"
        cr.execute(
            "INSERT INTO ir_logging (name, type, level, message, path, line, func, dbname, create_date)"
            " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(), now())",
            ('purchase_order_export', _logger_msg % (action.name, action.id),
             __file__, '0', 'migrate'),
        )
