{
    'name': "Replan WorkOrder — Popup prévisualisation",
    'version': "17.0.1.1.0",
    'license': "LGPL-3",
    'category': 'Manufacturing',
    'summary': 'Prévisualisation avant replanification + bouton Replanifier sur le formulaire OF',
    'depends': ['mrp_replan_workorder'],
    'data': [
        'security/ir.model.access.csv',
        'views/mrp_replan_preview_wizard_views.xml',
        'views/mrp_production_button_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
