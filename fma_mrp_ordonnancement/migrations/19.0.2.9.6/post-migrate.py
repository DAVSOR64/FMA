# -*- coding: utf-8 -*-
"""Calcul initial des colonnes STG et Retard.

Deux champs stockés apparaissent : leurs colonnes sont créées par la mise à
jour, mais Odoo ne calcule pas les valeurs des enregistrements existants.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['mrp.production']._cron_fma_recalcul_ordonnancement()
    _logger.info("Ordonnancement FMA : colonnes STG et Retard calculées.")
