import re
from odoo import api, SUPERUSER_ID

# res.partner.mobile was removed in Odoo v19.
# Remove any t-field, t-att-src, or standalone reference to .mobile on partner.
_MOBILE_PATTERNS = [
    # <span t-field="o.partner_id.mobile"/> or <span t-field="o.sale_id.partner_id.mobile"/>
    (re.compile(r'<[^>]+t-field="[^"]*\.mobile"[^/]*/>', re.IGNORECASE), ''),
    (re.compile(r'<[^>]+t-field="[^"]*\.mobile"[^>]*>[^<]*</[^>]+>', re.IGNORECASE), ''),
    # Mobile: <span ...mobile"/>  — with surrounding text label on same line
    (re.compile(r'[^\n<]*Mobile\s*:\s*<[^>]+t-field="[^"]*\.mobile"[^/]*/>\s*<br\s*/>', re.IGNORECASE), ''),
    (re.compile(r'\s*Mobile\s*:\s*<[^>]+t-field="[^"]*\.mobile"[^/]*/>', re.IGNORECASE), ''),
]


def _remove_mobile(arch):
    for pattern, replacement in _MOBILE_PATTERNS:
        arch = pattern.sub(replacement, arch)
    return arch


def migrate(cr, version):
    """Remove res.partner.mobile field references from all DB-stored views.

    partner.mobile was removed in Odoo v19. Studio-customized report views
    (e.g. stock.report_delivery_document) may still reference it, causing
    KeyError on report rendering.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})

    views = env['ir.ui.view'].search([
        ('arch_db', 'ilike', '.mobile'),
    ])

    for view in views:
        arch = view.arch_db or ''
        if '.mobile' not in arch:
            continue
        new_arch = _remove_mobile(arch)
        if new_arch != arch:
            view.with_context(no_cow=True).write({'arch_db': new_arch})
            cr.execute(
                "INSERT INTO ir_logging"
                " (name, type, level, message, path, line, func, dbname, create_date)"
                " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(), now())",
                ('custom',
                 f"Migration 19.0.1.0.5: removed .mobile field from view '{view.name}' (id={view.id})",
                 __file__, '0', 'migrate'),
            )
