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
    # 1.2.0 : plus de nomenclature d'affaire ni de ligne « projet » quand
    # l'import pricer est installe -- chaque menuiserie porte desormais sa
    # nomenclature et sa gamme. Sans le pricer (production), rien ne change.
    # 1.1.4 : les articles saisis a la main dans LOGIKAL sont marques
    # (fma_article_libre) et portent leur designation en reference interne.
    # Leur reference « _LB<n> » suit le rang dans le fichier depose et change
    # d'un export a l'autre : elle ne pouvait pas servir a les reconnaitre.
    # 1.4.0 : les menuiseries sont suivies au NUMERO DE SERIE. Sans cela,
    # une ligne de 4 menuiseries donne un ordre de 4 et declarer la
    # premiere oblige a creer un reliquat de 3, puis de 2, puis de 1 :
    # l'ecran Atelier devient inutilisable alors que le cas d'usage est
    # justement de declarer menuiserie par menuiserie. Reprise de
    # l'existant en post-migrate, hors articles deja mouvementes.
    # 1.5.0 : la regle de construction de la reference LOGIKAL sort de la
    # boucle d'import et devient une fonction, que l'import pricer appelle
    # pour retrouver les articles que ce module a crees.
    "version": "19.0.1.5.0",
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
