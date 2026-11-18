# -*- coding: utf-8 -*-
"""Donne un nom aux articles de menuiserie que l'import a crees sans nom.

Le connecteur nommait l'article d'apres Elevations.Description, et rien
d'autre : une designation laissee vide dans LOGIKAL donnait un article sans
nom. Odoo n'affiche alors rien du tout pour le modele d'article, et sa
nomenclature apparait en blanc dans la liste.

La reprise prend la designation de la ligne de commande la plus recente qui
porte l'article ; quand la ligne ne porte que la reference, l'article prend
son repere, en attendant le prochain depot du fichier. Elle ne touche a aucun
nom saisi a la main : ceux-la sont listes dans le journal.

Rejouable : un article deja nomme n'est plus candidat.

A ce stade du chargement, les modules qui dependent de celui-ci ne sont pas
encore la : les semi-finis et leurs nomenclatures sont repris une seconde fois
par fma_pricer_import, quand il est installe, avec la meme fonction.
"""
import logging

from odoo import SUPERUSER_ID, api

from odoo.addons.sqlite_connector import noms_articles

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    rapport = noms_articles.reprise(env, appliquer=True)
    for ligne in noms_articles.lignes_rapport(rapport, limite=0):
        _logger.info("Noms des articles de menuiserie : %s", ligne)
