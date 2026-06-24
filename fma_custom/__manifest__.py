# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "FMA: Custom",
    "description": """
        Custom module delete button on email.
    """,
    "summary": "Custom delete button",
    "author": "Odoo PS",
    "version": "19.0.1.0.2",
    "depends": ["custom", "hr"],
    "data": [
        "views/mail_templates.xml",
    ],
    "post_init_hook": "post_init_hook",
    "license": "LGPL-3",
}
