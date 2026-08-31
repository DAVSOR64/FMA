# -*- coding: utf-8 -*-
"""Amorçage à l'installation du module."""
import logging

_logger = logging.getLogger(__name__)

# Familles de produit dont la correspondance est certaine, d'apres le
# referentiel FMA.
FAMILLES_CONNUES = {
    '01_PROFILS_BARRES_TOLES': 'profil',
}

# Categories de produit. C'est le niveau qui porte reellement l'information
# sur les articles achetes : un couvre-joint TECHNAL ou un vitrage TIV ont
# leur categorie renseignee sans forcement avoir de triplet famille.
# 02_REMPLISSAGE est rattachee au vitrage, ce qui est deja la convention de
# fma_custom (_is_vitrage). Si des panneaux y sont melanges, les distinguer
# ensuite au niveau sous-famille.
CATEGORIES_CONNUES = {
    '01_PROFILS_BARRES_TOLES': 'profil',
    '02_REMPLISSAGE': 'vitrage',
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


def _rattacher_categories(env):
    """Amorce la famille d'approvisionnement sur les catégories de produit."""
    Categorie = env['product.category']
    total = 0
    for fragment, famille_appro in CATEGORIES_CONNUES.items():
        categories = Categorie.search([
            ('name', '=ilike', fragment),
            ('fma_famille_appro', '=', False),
        ])
        if categories:
            categories.write({'fma_famille_appro': famille_appro})
            total += len(categories)
    _logger.info(
        "Ordonnancement FMA : %s catégorie(s) de produit rattachée(s). "
        "Les autres restent à renseigner dans Séquencement > Familles par "
        "catégorie.", total,
    )


def _recalcul_initial(env):
    """Premier calcul sur les OF ouverts."""
    env['mrp.production']._cron_fma_recalcul_ordonnancement()


def post_init_hook(env):
    _typer_postes_de_charge(env)
    _rattacher_familles(env)
    _rattacher_categories(env)
    _recalcul_initial(env)
