# -*- coding: utf-8 -*-
"""Recalcul complet après recentrage sur la commande de vente résolue.

Les champs dérivés du devis — date d'engagement, bons de livraison, nombre de
repères, et donc les scores — lisaient sale_line_id, qui n'est pas toujours
renseigné chez FMA. Ils sont désormais dérivés de fma_sale_order_id, qui
retombe sur x_studio_mtn_mrp_sale_order.

On en profite pour retyper les postes de charge : un poste ajouté depuis
l'installation, ou dont le libellé a changé, ne serait rattaché à aucun type
et ses heures ne seraient comptées nulle part.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})

    postes = env['mrp.workcenter'].search([('fma_poste_type', '=', False)])
    types = 0
    for poste in postes:
        poste_type = env['mrp.workcenter']._fma_deviner_poste_type(poste.name)
        if poste_type:
            poste.fma_poste_type = poste_type
            types += 1
    if types:
        _logger.info("Ordonnancement FMA : %s poste(s) de charge typé(s).", types)

    env['mrp.production']._cron_fma_recalcul_ordonnancement()
    _logger.info(
        "Ordonnancement FMA : recalcul complet effectué depuis la version %s.",
        version,
    )
