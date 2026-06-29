import re
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Replace tax_id → tax_ids in ALL ir.ui.view records that reference it.

    The 19.0.1.0.2 migration was updated to be model-agnostic but could not
    re-run because the DB already registered that version. This 19.0.1.0.3
    migration ensures QWeb report templates (e.g. sale.report_saleorder_document,
    id=1010) are also patched — they have no model set on ir.ui.view and were
    therefore missed by the original model-filtered migration.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})

    views = env['ir.ui.view'].search([
        ('arch_db', 'ilike', 'tax_id'),
    ])

    for view in views:
        if 'tax_id' not in (view.arch_db or ''):
            continue
        new_arch = re.sub(r'\btax_id\b(?!s)', 'tax_ids', view.arch_db)
        if new_arch != view.arch_db:
            view.with_context(no_cow=True).write({'arch_db': new_arch})
            cr.execute(
                "INSERT INTO ir_logging"
                " (name, type, level, message, path, line, func, dbname, create_date)"
                " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(), now())",
                ('custom_sale_order',
                 f"Migration 19.0.1.0.3: patched tax_id→tax_ids in view '{view.name}' (id={view.id})",
                 __file__, '0', 'migrate'),
            )
