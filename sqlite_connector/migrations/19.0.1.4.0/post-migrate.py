# -*- coding: utf-8 -*-
"""Passe les menuiseries existantes au suivi par numero de serie.

Sans ce suivi, une ligne de 4 menuiseries donne un ordre de 4, et declarer la
premiere oblige a creer un reliquat de 3, puis de 2, puis de 1. Avec, l'ecran
Atelier enregistre une menuiserie a la fois, l'ordre reste ouvert, et chaque
exemplaire garde son identite jusqu'au SAV.

Le connecteur pose desormais tracking='serial' a la creation. Cette reprise
fait la meme chose sur l'existant, mais SEULEMENT la ou c'est licite.

Odoo refuse de changer le suivi d'un article qui a deja bouge : les
mouvements passes n'ont pas de numero, et leur en inventer un serait
falsifier une tracabilite. On ne force donc rien. Les articles deja
mouvementes gardent leur suivi actuel et sont NOMMES dans le journal : ce
sont des affaires anciennes, et la question ne se pose que si l'on veut
reprendre leur production.

Les menuiseries se reconnaissent a la signature que le connecteur leur pose :
vendables, non achetables, et porteuses d'une position. Le vitrage est
achetable, les semi-finis ne sont pas vendables -- ni l'un ni l'autre n'entre
donc dans le lot.
"""
import logging

_logger = logging.getLogger(__name__)

CANDIDATS = """
    SELECT pt.id, pt.default_code
      FROM product_template pt
     WHERE pt.sale_ok IS TRUE
       AND pt.purchase_ok IS FALSE
       AND pt.tracking <> 'serial'
       AND EXISTS (
           SELECT 1 FROM product_product pp
            WHERE pp.product_tmpl_id = pt.id
              AND pp.x_studio_position IS NOT NULL
       )
"""

A_BOUGE = """
    SELECT 1 FROM stock_move_line sml
      JOIN product_product pp ON pp.id = sml.product_id
     WHERE pp.product_tmpl_id = %s
     LIMIT 1
"""


def migrate(cr, version):
    cr.execute(
        """SELECT 1 FROM information_schema.columns
            WHERE table_name = 'product_product'
              AND column_name = 'x_studio_position'"""
    )
    if not cr.fetchone():
        _logger.info(
            "Suivi serie : x_studio_position absent, reprise sans objet")
        return

    cr.execute(CANDIDATS)
    candidats = cr.fetchall()
    _logger.info("Suivi serie : %s menuiserie(s) a examiner", len(candidats))

    passes, bloques = [], []
    for tmpl_id, code in candidats:
        cr.execute(A_BOUGE, (tmpl_id,))
        if cr.fetchone():
            bloques.append(code or tmpl_id)
            continue
        passes.append(tmpl_id)

    if passes:
        cr.execute(
            "UPDATE product_template SET tracking = 'serial'"
            " WHERE id = ANY(%s)",
            (passes,),
        )
        _logger.info(
            "Suivi serie : %s menuiserie(s) passees au numero de serie",
            cr.rowcount)

    if bloques:
        _logger.warning(
            "Suivi serie : %s menuiserie(s) ont deja des mouvements et "
            "gardent leur suivi actuel. Les reprendre en production demandera "
            "de leur donner des numeros a la main.", len(bloques))
        for code in bloques[:25]:
            _logger.warning("   %s", code)
