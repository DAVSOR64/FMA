# -*- coding: utf-8 -*-
"""Donne une reference LOGIKAL aux articles libres deja crees.

Une ligne saisie a la main dans LOGIKAL n'a ni code, ni GUID, ni hashcode :
sa designation est tout ce qui la distingue. Le connecteur ne la reportait
nulle part, et l'import pricer devait donc reconnaitre ces articles a leur
NOM -- un champ que n'importe qui peut renommer.

Le connecteur ecrit desormais la designation dans x_studio_ref_int_logikal a
la creation. Cette reprise fait la meme chose pour les articles libres deja
en base : on recopie le nom, une fois, dans le champ technique. Le nom peut
ensuite bouger sans casser le rattachement.

Les articles libres se reconnaissent a leur reference « ..._LB<n> », posee
par le connecteur lui-meme. Le champ Studio peut vivre sur le modele ou sur
la variante selon la facon dont il a ete cree : on traite la table qui le
porte, sans rien supposer.
"""
import logging

_logger = logging.getLogger(__name__)

# (table, table portant default_code et name)
CIBLES = [
    ("product_template", "product_template", "id"),
    ("product_product", "product_template", "product_tmpl_id"),
]


def migrate(cr, version):
    for table, source, lien in CIBLES:
        cr.execute(
            """SELECT 1 FROM information_schema.columns
                WHERE table_name = %s AND column_name = 'x_studio_ref_int_logikal'""",
            (table,),
        )
        if not cr.fetchone():
            continue

        cr.execute(
            """UPDATE {table} t
                  SET x_studio_ref_int_logikal = COALESCE(
                          s.name->>'fr_FR', s.name->>'en_US')
                 FROM {source} s
                WHERE s.id = t.{lien}
                  AND s.default_code LIKE '%%\\_LB%%'
                  AND COALESCE(t.x_studio_ref_int_logikal, '') = ''
                  AND COALESCE(s.name->>'fr_FR', s.name->>'en_US', '') <> ''
            """.format(table=table, source=source, lien=lien)
        )
        _logger.info(
            "Articles libres (%s) : %s references LOGIKAL reprises depuis le nom",
            table, cr.rowcount)
        return

    _logger.info(
        "x_studio_ref_int_logikal absent : reprise des articles libres sans objet")
