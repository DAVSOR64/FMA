# -*- coding: utf-8 -*-
"""Amorce le verrou « Fabrication lancée » sur les affaires existantes.

so_fab_lancee est un champ simple, ecrit par _fma_sync_fab_lancee a la
creation et a l'ecriture. Les commandes deja en base n'ont connu ni l'une ni
l'autre depuis sa creation : sans cette reprise, leur delai confirme et leur
date de BPE resteraient modifiables alors que l'atelier est lance, et ne se
refermeraient qu'au prochain passage sur le Bon pour fabrication.

En SQL : un write() sur plusieurs milliers de commandes declencherait tous
les calculs stockes de sale.order, pour poser un booleen que rien ne lit en
amont.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """UPDATE sale_order
              SET so_fab_lancee = (so_date_bon_pour_fab IS NOT NULL)
            WHERE so_fab_lancee IS DISTINCT FROM (so_date_bon_pour_fab IS NOT NULL)"""
    )
    _logger.info(
        "Verrou « Fabrication lancée » pose sur %s commande(s).", cr.rowcount)
