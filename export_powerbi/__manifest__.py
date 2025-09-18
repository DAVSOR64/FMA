{
    'name': 'Export PowerBI',
    'version': '17.0.1.1',
    'summary': 'Export clients, commandes, factures vers SFTP pour Power BI',
    'depends': ['base', 'sale', 'account', 'custom'], 
    'data': [
        'data/ir_cron.xml',
        'views/export_config_views.xml',
    ],
    'installable': True,
    'auto_install': False
}
