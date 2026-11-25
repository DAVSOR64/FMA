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
    # 1.5.1 : la regle de reference reconnait « WICONA FRANCE » comme
    # « WICONA » — le libelle du fichier n'est pas toujours le code.
    # 1.6.0 : une menuiserie dont la designation est vide dans LOGIKAL ne
    # nait plus sans nom (designation automatique, puis repere), et le nom
    # suit la designation au reimport tant qu'il n'a pas ete saisi a la main
    # (nouvelle colonne product_template.fma_nom_importe). Reprise en
    # post-migrate des articles deja crees sans nom, d'apres leur ligne de
    # commande.
    # 1.20.0 : le poste de charge d'un temps vient d'une TABLE PAR SITE, et
    # non d'une cascade de tests sans cas final : un TimeType inconnu du
    # site — le 10 chez F2M, le 12 chez FMA — laissait le poste de la ligne
    # precedente, et les minutes grossissaient en silence la mauvaise
    # operation. Un TimeType inconnu, comme un poste de charge absent du
    # referentiel, est desormais trace.
    # 1.21.0 : la destination du vitrage s'AFFICHE. Elle etait lue dans
    # Glass.Info2, ecrite sur l'article, recopiee sur la ligne d'achat,
    # elle decoupait les bons et sortait le vitrage de chantier du lot --
    # sans apparaitre sur un seul ecran. Impossible de verifier qu'une
    # affaire avait bien ete reprise : releve sur PETIFILS (A25-09-03010),
    # dont les huit vitrages portent PALETTE. Elle est desormais sur la
    # fiche article, avec deux filtres et un regroupement.
    # Au passage : un remplissage qui n'est pas du vitrage recoit CHARIOT en
    # clair au lieu d'un Info2 vide. La destination ne se decide que pour le
    # vitrage, un panneau est systematiquement pose en atelier. Le repli
    # donnait deja chariot, mais en journalisant une non-conformite
    # « (vide) » par panneau et par import, la ou le vide est la norme.
    "version": "19.0.1.21.0",
    "description": """

    """,
    # « purchase » : la destination du vitrage lue dans LOGIKAL decide
    # de la commande d'achat, voir models/purchase_order.py.
    "depends": ["mail", "sale", "product", "purchase", "stock"],
    "data": [
        "views/sqlite_connector.xml",
        "views/product_views.xml",
        "security/ir.model.access.csv",
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
