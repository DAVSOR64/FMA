# -*- coding: utf-8 -*-
{
    'name': 'FMA/F2M - Laquage sous-traitance',
    'version': '17.0.1.1.0',
    'category': 'Manufacturing',
    'summary': 'Planification du laquage externe F2M, création achat et coût de sous-traitance',
    'author': 'Paxo Consulting',
    'depends': [
        'mrp_capacity_planning',
        'purchase_stock',
        'stock',
        'sale_mrp',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_config_parameter.xml',
        'views/fma_laquage_subcontractor_views.xml',
        'views/mrp_production_views.xml',
        'views/mrp_workorder_views.xml',
        'wizard/fma_laquage_plan_wizard_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
