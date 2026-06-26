from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Replace t-name="kanban-box" → t-name="card" in all Kanban views.

    In Odoo v19, the Kanban card template was renamed from "kanban-box" to
    "card". Studio-generated kanban views stored in the DB still use the old
    name, causing "Missing 'card' template" errors when opening kanban views.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})

    views = env['ir.ui.view'].search([
        ('type', '=', 'kanban'),
        ('arch_db', 'ilike', 'kanban-box'),
    ])

    for view in views:
        if 'kanban-box' not in (view.arch_db or ''):
            continue
        new_arch = view.arch_db.replace(
            't-name="kanban-box"', 't-name="card"'
        ).replace(
            "t-name='kanban-box'", "t-name='card'"
        )
        if new_arch != view.arch_db:
            view.with_context(no_cow=True).write({'arch_db': new_arch})
            cr.execute(
                "INSERT INTO ir_logging"
                " (name, type, level, message, path, line, func, dbname, create_date)"
                " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(), now())",
                ('custom',
                 f"Migration 19.0.1.0.3: patched kanban-box→card in view '{view.name}' (id={view.id})",
                 __file__, '0', 'migrate'),
            )
