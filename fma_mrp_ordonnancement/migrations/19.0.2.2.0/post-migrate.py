# -*- coding: utf-8 -*-
"""Recalcul complet des champs d'ordonnancement.

Odoo ne recalcule pas un champ stocké dont seule la *formule* change : la
colonne existe déjà, l'ORM la laisse telle quelle. Les valeurs héritées de la
version précédente restent donc en base, silencieusement fausses.

C'était le cas de fma_nb_reperes, qui affichait encore la somme des
multiplicateurs du champ de complexité (« A*20 » + « M*7 » = 27) alors que la
règle est devenue « nombre de lignes de devis ».

Toute version qui change la sémantique d'un champ stocké doit s'accompagner
d'un script comme celui-ci.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['mrp.production']._cron_fma_recalcul_ordonnancement()
    _logger.info(
        "Ordonnancement FMA : recalcul complet effectué après passage depuis "
        "la version %s.", version,
    )
