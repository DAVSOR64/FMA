# -*- coding: utf-8 -*-
"""Classe les lignes d'achat par famille, puis recalcule les OF.

purchase.order.line.fma_famille_appro est un nouveau champ stocké : il doit
être calculé sur l'existant avant que les colonnes d'approvisionnement de
l'OF, qui s'appuient désormais dessus, soient reconstruites.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})

    env['purchase.order.line']._fma_recalculer_familles()
    _logger.info("Ordonnancement FMA : lignes d'achat reclassées par famille.")

    env['mrp.production']._cron_fma_recalcul_ordonnancement()
    _logger.info(
        "Ordonnancement FMA : recalcul complet effectué depuis la version %s.",
        version,
    )
