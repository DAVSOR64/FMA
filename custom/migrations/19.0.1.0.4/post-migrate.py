import re
from odoo import api, SUPERUSER_ID

# kanban_image('model', 'field', expr) was removed in v19.
# Replace with a direct /web/image/ URL using t-attf-src.
_KANBAN_IMAGE_RE = re.compile(
    r't-att-src="kanban_image\(\'([^\']+)\'\s*,\s*\'([^\']+)\'\s*,\s*([^)]+)\)"'
)
_KANBAN_IMAGE_RE_SQ = re.compile(
    r"t-att-src='kanban_image\(\"([^\"]+)\"\s*,\s*\"([^\"]+)\"\s*,\s*([^)]+)\)'"
)


def _replace_kanban_image(arch):
    def replacer(m):
        model = m.group(1)
        field = m.group(2)
        expr = m.group(3).strip()
        return f't-attf-src="/web/image/{model}/{{{{{expr}}}}}/{field}"'

    arch = _KANBAN_IMAGE_RE.sub(replacer, arch)
    arch = _KANBAN_IMAGE_RE_SQ.sub(replacer, arch)
    return arch


def migrate(cr, version):
    """Replace kanban_image() helper calls with direct /web/image/ URLs.

    kanban_image('model', 'field', id) no longer exists in Odoo v19 ctx,
    causing TypeError when rendering kanban cards built with Studio in v17.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})

    views = env['ir.ui.view'].search([
        ('type', '=', 'kanban'),
        ('arch_db', 'ilike', 'kanban_image'),
    ])

    for view in views:
        if 'kanban_image' not in (view.arch_db or ''):
            continue
        new_arch = _replace_kanban_image(view.arch_db)
        if new_arch != view.arch_db:
            view.with_context(no_cow=True).write({'arch_db': new_arch})
            cr.execute(
                "INSERT INTO ir_logging"
                " (name, type, level, message, path, line, func, dbname, create_date)"
                " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(), now())",
                ('custom',
                 f"Migration 19.0.1.0.4: patched kanban_image in view '{view.name}' (id={view.id})",
                 __file__, '0', 'migrate'),
            )
        else:
            # Pattern didn't match regex — log for manual review
            cr.execute(
                "INSERT INTO ir_logging"
                " (name, type, level, message, path, line, func, dbname, create_date)"
                " VALUES (%s, 'server', 'WARNING', %s, %s, %s, %s, current_database(), now())",
                ('custom',
                 f"Migration 19.0.1.0.4: kanban_image found but pattern unmatched in view '{view.name}' (id={view.id}) — manual fix needed",
                 __file__, '0', 'migrate'),
            )
