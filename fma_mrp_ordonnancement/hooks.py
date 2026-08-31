# -*- coding: utf-8 -*-
"""Amorçage à l'installation du module."""
import logging

from .models.constants import FMA_CATEGORIES_APPRO_KEYS

_logger = logging.getLogger(__name__)

# Listes reprises telles quelles des formules J2, K2, L2 et M2 de l'onglet PO
# du classeur « Ordre de production FMA - Copie.xlsm ». Elles ne servent qu'à
# l'amorçage : ensuite, la famille se règle sur la fiche fournisseur.
FOURNISSEURS_PAR_FAMILLE = {
    'profil': [
        "TECHNAL", "WICONA HBS", "SAPA", "REYNAERS ALUMINIUM", "SCHUCO",
    ],
    'vitrage': [
        "VIV", "TIV", "MACOCCO OUEST", "PYROGUARD", "POLFLAM", "PILGLINTON",
    ],
    'panneaux': [
        "ISOSTA PSI", "EMAILLERIE ALSACIENNE", "JANNEAU MENUISERIES",
        "RODENBERG", "SIPO",
    ],
    'complementaire': [
        "LOUINEAU", "ABC PLIAGE", "Genimeca 44", "LAVEIX QUINCAILLERIE",
        "BRAULT METALLERIE", "BUBENDORFF", "VOLET DU SUD", "AGORA", "ID ALU",
        "STMO", "MABELUX TECHNIC", "FOUSSIER", "SOPROFEN", "BVL SERRULAC",
        "ART", "LR METALLERIE SERRURERIE MECANO SOU", "ELIT",
        "MAILLES ET VEINAGES", "STG CINTRAGE",
    ],
}


def _typer_postes_de_charge(env):
    """Renseigne fma_poste_type sur les postes existants, d'après leur nom."""
    postes = env['mrp.workcenter'].search([('fma_poste_type', '=', False)])
    typés = 0
    for poste in postes:
        poste_type = env['mrp.workcenter']._fma_deviner_poste_type(poste.name)
        if poste_type:
            poste.fma_poste_type = poste_type
            typés += 1
    _logger.info("Ordonnancement FMA : %s poste(s) de charge typé(s).", typés)


def _categoriser_fournisseurs(env):
    """Amorce la famille d'approvisionnement des fournisseurs connus."""
    Partner = env['res.partner']
    total = 0
    for famille, noms in FOURNISSEURS_PAR_FAMILLE.items():
        if famille not in FMA_CATEGORIES_APPRO_KEYS:
            continue
        for nom in noms:
            partenaires = Partner.search([
                ('name', '=ilike', nom),
                ('fma_categorie_appro', '=', False),
            ])
            if partenaires:
                partenaires.write({'fma_categorie_appro': famille})
                total += len(partenaires)
    _logger.info("Ordonnancement FMA : %s fournisseur(s) catégorisé(s).", total)


def _recalcul_initial(env):
    """Premier calcul sur les OF ouverts."""
    env['mrp.production']._cron_fma_recalcul_ordonnancement()


def post_init_hook(env):
    _typer_postes_de_charge(env)
    _categoriser_fournisseurs(env)
    _recalcul_initial(env)
