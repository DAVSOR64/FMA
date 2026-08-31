# -*- coding: utf-8 -*-
"""Recalcul après élargissement de la résolution des commandes d'achat.

Deux changements imposent de reconstruire les colonnes d'approvisionnement :
les achats sont désormais aussi retrouvés côté commande de vente, et le
complémentaire devient la famille par défaut.
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
        "Ordonnancement FMA : recalcul complet effectué depuis la version %s.",
        version,
    )
