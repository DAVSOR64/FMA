# -*- coding: utf-8 -*-
"""Rattache les catégories de produit puis recalcule les approvisionnements.

La famille d'approvisionnement était portée par product.family seul. Or les
articles achetés portent leur catégorie (« All / 01_PROFILS_BARRES_TOLES »,
« All / 02_REMPLISSAGE ») sans avoir nécessairement de triplet famille : les
colonnes d'approvisionnement retombaient donc toutes sur « Aucune commande »
alors que les commandes d'achat étaient bien retrouvées.
"""
import logging

_logger = logging.getLogger(__name__)

CATEGORIES_CONNUES = {
    '01_PROFILS_BARRES_TOLES': 'profil',
    '02_REMPLISSAGE': 'vitrage',
}


def migrate(cr, version):
    if not version:
        return
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})

    total = 0
    for fragment, famille in CATEGORIES_CONNUES.items():
        categories = env['product.category'].search([
            ('name', '=ilike', fragment),
            ('fma_famille_appro', '=', False),
        ])
        if categories:
            categories.write({'fma_famille_appro': famille})
            total += len(categories)
    _logger.info(
        "Ordonnancement FMA : %s catégorie(s) rattachée(s) à une famille.",
        total,
    )

    env['mrp.production']._cron_fma_recalcul_ordonnancement()
    _logger.info(
        "Ordonnancement FMA : recalcul complet effectué depuis la version %s.",
        version,
    )
