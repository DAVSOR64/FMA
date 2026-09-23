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
    # 1.1.4 : les articles saisis a la main dans LOGIKAL sont marques
    # (fma_article_libre) et portent leur designation en reference interne.
    # Leur reference « _LB<n> » suit le rang dans le fichier depose et change
    # d'un export a l'autre : elle ne pouvait pas servir a les reconnaitre.
    "version": "19.0.1.1.4",
    "description": """

    """,
    "depends": ["mail", "sale", "product"],
    "data": [
        "views/sqlite_connector.xml",
        "views/product_views.xml",
        "security/ir.model.access.csv",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
