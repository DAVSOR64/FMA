# -*- coding: utf-8 -*-
"""Recalcul après retrait du début de débit calculé et ajout des signaux.

fma_date_debut_debit est supprimé : le début de débit redevient date_start,
champ natif de l'ordre de fabrication. Sa colonne subsiste en base sans être
lue, l'ORM ne supprimant pas les colonnes orphelines ; elle disparaîtra à la
prochaine désinstallation.
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
