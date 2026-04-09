{
    'name': 'MRP FMA Planning Unified',
    'version': '17.0.1.0.0',
    'summary': 'Réordonnancement FMA + recalcul macro batch des OF non démarrés',
    'depends': [
        'mrp',
        'mrp_replan_workorder',
        'mrp_replan_workorder_popup'
    ],
    'data': [
        'views/mrp_production_views.xml',
        'data/ir_cron.xml'
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3'
}
