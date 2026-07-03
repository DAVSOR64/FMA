import re

from odoo import api, SUPERUSER_ID

# Odoo Studio's sale.order.form customization view moves the (now-removed
# in v19) sale.order.analytic_account_id field next to x_studio_projet via a
# nested <xpath position="move">. Since that field no longer exists, view
# combination for this view used to fail outright, and Odoo's own recovery
# mechanism responded by flipping the offending view to active=False --
# silently dropping the *entire* customization (x_studio_projet,
# x_studio_numro_iziqo, x_studio_avancement, x_studio_gamme, x_studio_srie,
# x_studio_commercial_1, etc.) from the quotation/order form. Fixing the
# arch alone is not enough: the view must also be reactivated.
_BROKEN_MOVE_RE = re.compile(
    r"\s*<xpath\s+expr=\"//field\[@name='analytic_account_id'\]\"\s+position=\"move\"\s*/>\s*\n?"
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute(
        "SELECT id FROM ir_ui_view"
        " WHERE model = 'sale.order' AND arch_db::text ILIKE %s",
        ('%analytic_account_id%',),
    )
    views = env['ir.ui.view'].browse([r[0] for r in cr.fetchall()])
    fixed = env['ir.ui.view']
    for view in views:
        for lang, _name in env['res.lang'].get_installed():
            view_lang = view.with_context(lang=lang)
            arch = view_lang.arch_db
            if not arch or 'analytic_account_id' not in arch:
                continue
            patched = _BROKEN_MOVE_RE.sub('\n', arch)
            if patched != arch:
                view_lang.write({'arch_db': patched})
                fixed |= view
        if not view.active:
            view.write({'active': True})
            fixed |= view
    if fixed:
        cr.execute(
            "INSERT INTO ir_logging"
            " (name, type, level, message, path, line, func, dbname, create_date)"
            " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(), now())",
            ('fma_sale_order_custom',
             f"Migration 19.0.1.0.3: removed dead analytic_account_id xpath move from view(s) {fixed.ids}",
             __file__, '0', 'migrate'),
        )
