# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Filet de sécurité pour les colonnes Spacer / Forme des lignes d'achat.

    x_studio_spacer_2 et x_studio_forme sont des champs stockés recopiés de
    l'article (product.product.x_studio_spacer / x_studio_type). Ils
    n'étaient affichés nulle part jusqu'ici : une ligne créée avant que
    l'article ne soit renseigné (ou par une écriture SQL / un import) a pu
    rester à NULL sans que rien ne déclenche de recalcul -- les deux
    nouvelles colonnes apparaîtraient alors vides sur des lignes vitrage
    dont l'article porte bien la valeur.

    Rattrapage volontairement limité aux lignes NULL : une valeur déjà
    présente n'est jamais écrasée.
    """
    for line_column, product_column in (
        ("x_studio_spacer_2", "x_studio_spacer"),
        ("x_studio_forme", "x_studio_type"),
    ):
        cr.execute(
            f"UPDATE purchase_order_line pol"
            f"    SET {line_column} = pp.{product_column}"
            f"   FROM product_product pp"
            f"  WHERE pol.product_id = pp.id"
            f"    AND pol.{line_column} IS NULL"
            f"    AND pp.{product_column} IS NOT NULL"
        )
        updated = cr.rowcount
        if not updated:
            continue

        cr.execute(
            "INSERT INTO ir_logging"
            " (name, type, level, message, path, line, func, dbname, create_date)"
            " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(), now())",
            ("custom",
             f"Migration 19.0.1.0.31: renseigné {line_column} sur {updated}"
             f" ligne(s) de commande d'achat",
             __file__, "0", "migrate"),
        )
