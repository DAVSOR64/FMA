# -*- coding: utf-8 -*-
"""Marque les articles libres deja crees, et leur donne une reference.

Une ligne saisie a la main dans LOGIKAL n'a ni code article, ni GUID, ni
hashcode : sa designation est tout ce qui la distingue. Le connecteur ne la
reportait nulle part, et l'import pricer devait reconnaitre ces articles a
leur NOM -- un champ que n'importe qui peut renommer.

Le connecteur pose desormais deux reperes a la creation : fma_article_libre,
qui dit ce qu'est l'article, et x_studio_ref_int_logikal, qui dit lequel.
Cette reprise fait la meme chose sur l'existant, une fois, a partir de ce que
la base porte deja : la reference « ..._LB<n> » fabriquee par le connecteur,
et le nom.

Aucun parametre n'est passe a execute() : les motifs LIKE s'ecrivent donc avec
un seul %, sans quoi psycopg les transmettrait tels quels a PostgreSQL.
"""
import logging

_logger = logging.getLogger(__name__)

# Le champ Studio vit sur le modele ou sur la variante selon la facon dont il
# a ete cree : on traite la table qui le porte, sans rien supposer.
# (table a mettre a jour, table portant default_code et name, colonne de lien)
CIBLES = [
    ("product_template", "product_template", "id"),
    ("product_product", "product_template", "product_tmpl_id"),
]


def migrate(cr, version):
    # La marque d'abord : c'est un champ du module, il existe forcement, et
    # c'est lui que l'import interroge desormais.
    cr.execute(
        r"""UPDATE product_template
               SET fma_article_libre = TRUE
             WHERE default_code LIKE '%\_LB%'
               AND COALESCE(fma_article_libre, FALSE) = FALSE"""
    )
    _logger.info("Articles libres : %s articles marques", cr.rowcount)

    for table, source, lien in CIBLES:
        cr.execute(
            """SELECT 1 FROM information_schema.columns
                WHERE table_name = %s AND column_name = 'x_studio_ref_int_logikal'""",
            (table,),
        )
        if not cr.fetchone():
            continue

        cr.execute(
            r"""UPDATE {table} t
                   SET x_studio_ref_int_logikal = COALESCE(
                           s.name->>'fr_FR', s.name->>'en_US')
                  FROM {source} s
                 WHERE s.id = t.{lien}
                   AND s.default_code LIKE '%\_LB%'
                   AND COALESCE(t.x_studio_ref_int_logikal, '') = ''
                   AND COALESCE(s.name->>'fr_FR', s.name->>'en_US', '') <> ''
            """.format(table=table, source=source, lien=lien)
        )
        _logger.info(
            "Articles libres (%s) : %s references LOGIKAL reprises depuis le nom",
            table, cr.rowcount)
        return

    _logger.info(
        "x_studio_ref_int_logikal absent : references non reprises")
