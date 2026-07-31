from odoo import api, SUPERUSER_ID
from odoo.addons.fma_custom.hooks import _patch_hr_employee_studio_view


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _patch_hr_employee_studio_view(env)
