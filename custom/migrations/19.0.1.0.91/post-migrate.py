# -*- coding: utf-8 -*-
"""Reprise : le « Projet » des achats en cours qui ne l'ont pas.

La regle qui recopiait le projet de la commande lisait un champ que le devis
n'alimente plus ; les achats generes depuis l'ont donc vide. On le remplit ici
pour les achats non annules, sans declencher les autres automatismes (acheteur,
reference) : seul le projet manquant est pose.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Achat = env["purchase.order"].with_context(
        skip_studio_sync=True, fma_rattachement_auto=True, tracking_disable=True)
    achats = Achat.search([
        ("x_studio_projet_du_so", "=", False), ("state", "!=", "cancel")])
    poses = 0
    for achat in achats:
        try:
            with cr.savepoint():
                achat._sync_projet_du_so_from_sale_order()
                if achat.x_studio_projet_du_so:
                    poses += 1
        except Exception:  # un achat recalcitrant ne doit pas bloquer la mise a jour
            _logger.exception("Projet de l'achat %s : reprise impossible", achat.name)
    _logger.info(
        "Achats sans projet : %s examines, %s completes depuis leur commande.",
        len(achats), poses)
