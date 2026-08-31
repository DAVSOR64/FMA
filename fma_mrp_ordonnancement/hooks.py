# -*- coding: utf-8 -*-
"""Amorçage à l'installation du module."""
import logging

_logger = logging.getLogger(__name__)

# Familles de produit dont la correspondance est certaine, d'apres le
# referentiel FMA. 02_Remplissage n'y figure pas : elle recouvre a la fois le
# vitrage et les panneaux, la distinction se fait au niveau sous-famille.
FAMILLES_CONNUES = {
    '01_PROFILS_BARRES_TOLES': 'profil',
}


def _typer_postes_de_charge(env):
    """Renseigne fma_poste_type sur les postes existants, d'après leur nom.

    Couvre les libellés des deux ateliers : « Débit FMA » comme « Débit F2M ».
    """
    postes = env['mrp.workcenter'].search([('fma_poste_type', '=', False)])
    types = 0
    for poste in postes:
        poste_type = env['mrp.workcenter']._fma_deviner_poste_type(poste.name)
        if poste_type:
            poste.fma_poste_type = poste_type
            types += 1
    _logger.info("Ordonnancement FMA : %s poste(s) de charge typé(s).", types)


def _rattacher_familles(env):
    """Amorce la famille d'approvisionnement sur les familles certaines."""
    Famille = env['product.family']
    total = 0
    for code, famille_appro in FAMILLES_CONNUES.items():
        familles = Famille.search([
            '|', ('code', '=ilike', code), ('name', '=ilike', code),
            ('fma_famille_appro', '=', False),
        ])
        if familles:
            familles.write({'fma_famille_appro': famille_appro})
            total += len(familles)
    _logger.info(
        "Ordonnancement FMA : %s famille(s) de produit rattachée(s). "
        "Le vitrage et les panneaux se distinguent au niveau sous-famille "
        "(02_Remplissage) ; les complémentaires restent à définir.",
        total,
    )


def _recalcul_initial(env):
    """Premier calcul sur les OF ouverts."""
    env['mrp.production']._cron_fma_recalcul_ordonnancement()


def post_init_hook(env):
    _typer_postes_de_charge(env)
    _rattacher_familles(env)
    _recalcul_initial(env)
