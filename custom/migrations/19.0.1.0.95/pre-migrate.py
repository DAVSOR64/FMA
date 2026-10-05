# -*- coding: utf-8 -*-
"""Retour arriere de la reprise 19.0.1.0.93.

La 1.0.93 avait reparti le numero a 14 chiffres de company_registry en deux :
le SIRET dans fma_siret, les 9 premiers chiffres dans company_registry. Cette
separation est abandonnee : company_registry reste le SIRET.

Ne concerne que les bases ou la 1.0.93 a tourne (staging). En production la
colonne fma_siret n'existe pas : rien n'est fait, aucune donnee n'est touchee.

En pre-migrate, avant que la colonne du champ retire ne soit supprimee.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'res_partner' AND column_name = 'fma_siret'"
    )
    if not cr.fetchone():
        return
    cr.execute(
        """
        UPDATE res_partner
           SET company_registry = fma_siret
         WHERE fma_siret ~ '^[0-9]{14}$'
           AND COALESCE(company_registry, '') IN ('', left(fma_siret, 9))
        """
    )
    _logger.info(
        "SIRET : %s fiche(s) dont le numero a 14 chiffres revient dans "
        "company_registry.", cr.rowcount)
