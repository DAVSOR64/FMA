# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': "custom_colisage",

    'summary': """
        Short (1 phrase/line) summary of the module's purpose, used as
        subtitle on modules listing or apps.openerp.com""",

    'description': """
        Long description of module's purpose
    """,

    'author': "Odoo PS",
    'website': "http://www.yourcompany.com",

    'category': 'Uncategorized',
    'version': '17.0.1.0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'stock'],

    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
        # 'views/colisage.xml',  
    ],

    # Section pour inclure les fichiers statiques
    'assets': {
        'web.assets_backend': [
            'custom_colisage/static/src/img/lieu.png', # Chemin vers l'image à inclure
            'custom_colisage/static/src/img/camion.png',
            'custom_colisage/static/src/img/appel-telephonique.png',
            'custom_colisage/static/src/img/enveloppe.png',
        ],
    },

    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],

    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
