{
    'name': 'Export Groom XML vers SFTP',
    'version': '17.0.1.0.0',
    'author': 'DAVSOR',
    'depends': [
        'base',
        'sale',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        # 'views/export_sftp_scheduler_views.xml',  # si tu en crées
    ],
    'application': False,
    'installable': True,
}
