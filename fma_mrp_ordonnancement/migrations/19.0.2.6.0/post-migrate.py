# -*- coding: utf-8 -*-
"""Recalcul après passage des dates d'arrivée en Datetime.

Les colonnes de date perdaient un jour : date_planned est stocké en UTC, et
tronquer sans repasser en heure locale ramène « 24/08 00:00 » à « 23/08 ».
Les champs changent de type, leurs valeurs doivent être reconstruites.
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
