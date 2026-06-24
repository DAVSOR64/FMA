# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "FMA: Custom",
    "description": """
        Custom module delete button on email.
    """,
    "summary": "Custom delete button",
    "author": "Odoo PS",
    "version": "19.0.1.0.1",
    "depends": ["custom", "hr"],
    "data": [
        "views/mail_templates.xml",
        "views/hr_employee_access_fix.xml",
    ],
    "license": "LGPL-3",
}
