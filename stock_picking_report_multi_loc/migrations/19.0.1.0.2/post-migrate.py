from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Replace move_ids_without_package → move_ids in all ir.ui.view records.

    stock.picking.move_ids_without_package was removed in Odoo v19.
    Studio-generated or DB-stored views (e.g. stock.report_picking) may still
    reference the old field name, causing AttributeError on report rendering.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})

    views = env['ir.ui.view'].search([
        ('arch_db', 'ilike', 'move_ids_without_package'),
    ])

    for view in views:
        if 'move_ids_without_package' not in (view.arch_db or ''):
            continue
        new_arch = view.arch_db.replace('move_ids_without_package', 'move_ids')
        view.with_context(no_cow=True).write({'arch_db': new_arch})
        cr.execute(
            "INSERT INTO ir_logging"
            " (name, type, level, message, path, line, func, dbname, create_date)"
            " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(), now())",
            ('stock_picking_report_multi_loc',
             f"Migration 19.0.1.0.2: patched move_ids_without_package→move_ids in view '{view.name}' (id={view.id})",
             __file__, '0', 'migrate'),
        )
