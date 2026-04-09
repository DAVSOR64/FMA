{
    'name': 'MRP FMA Planning Unified V2',
    'version': '17.0.1.1.1',
    'summary': 'Réordonnancement FMA + recalcul macro batch + popup manuel',
    'depends': ['mrp', 'mail', 'mrp_replan_workorder', 'mrp_replan_workorder_popup', 'purchase'],
    'data': [
        'security/ir.model.access.csv',
        'views/mrp_production_views.xml',
        'wizards/mrp_recalc_planif_wizard_views.xml',
        'data/ir_cron.xml'
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3'
}
