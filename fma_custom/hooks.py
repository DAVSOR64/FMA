# -*- coding: utf-8 -*-
from lxml import etree

_STUDIO_VIEW_XMLID = (
    "studio_customization.odoo_studio_hr_emplo_77f50555-955f-47ab-a3d8-c686e649c1e2"
)


def post_init_hook(env):
    _patch_hr_employee_studio_view(env)


def _patch_hr_employee_studio_view(env):
    """Add groups='hr.group_hr_user' on the Print Badge button and the
    is_user_active span in the Studio hr.employee form customization.

    Both elements depend on fields only readable by hr.group_hr_user, but the
    Studio view exposes them to base.group_system as well, causing Access Rights
    Inconsistency warnings on every server start.
    """
    view = env.ref(_STUDIO_VIEW_XMLID, raise_if_not_found=False)
    if not view:
        return

    arch = etree.fromstring(view.arch.encode())
    changed = False

    for button in arch.xpath("//button[@name='720']"):
        if button.get("groups", "") != "hr.group_hr_user":
            button.set("groups", "hr.group_hr_user")
            changed = True

    for span in arch.xpath("//span"):
        if "is_user_active" in span.get("invisible", "") and span.get("groups", "") != "hr.group_hr_user":
            span.set("groups", "hr.group_hr_user")
            changed = True

    if changed:
        view.write({"arch": etree.tostring(arch, encoding="unicode")})
