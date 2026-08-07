{
    "name": "SQLite Connector",
    "category": "",
    "author": "Odoo PS",
    "sequence": 358,
    "summary": "",
    # 1.1.0 : references d'article fondees sur la position et non sur le rang
    # dans le fichier, pour qu'un export lot par lot retombe sur les memes
    # articles. Menuiserie : <affaire>_<position>. Vitrage :
    # <affaire>_<position>_<rang dans la position>.
    # 1.1.1 : la ligne de devis construisait encore sa reference sur le rang
    # (<n>_<affaire>) alors que l'article est cree en <affaire>_<position> :
    # elle ne retrouvait pas l'article et n'etait pas creee.
    "version": "19.0.1.1.1",
    "description": """

    """,
    "depends": ["mail", "sale"],
    "data": [
        "views/sqlite_connector.xml",
        "security/ir.model.access.csv",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
