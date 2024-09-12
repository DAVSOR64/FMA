{
    'name': 'Odoo Excel Attachment on OUT',
    'version': '1.0',
    'category': 'Tools',
    'summary': 'Generate Excel file and attach it when a record goes OUT',
    'depends': ['base', 'sale', 'mail'],  # 'sale' est un exemple
    'data': [
        # Les fichiers XML qui pourraient être nécessaires pour des vues ou des actions
    ],
    'installable': True,
    'auto_install': False,
}
