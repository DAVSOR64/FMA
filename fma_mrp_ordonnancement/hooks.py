# -*- coding: utf-8 -*-
"""Amorçage à l'installation du module."""
import logging

_logger = logging.getLogger(__name__)

# Catégories de produit connues, reprises de fma_custom.sale_order, qui
# identifie déjà le vitrage par ce biais. Le reste du paramétrage se fait en
# configuration : la liste des familles est courte, contrairement à celle des
# fournisseurs que le classeur maintenait en dur dans ses formules.
CATEGORIES_CONNUES = {
    'vitrage': ("all vitrage", "All / 02_REMPLISSAGE"),
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


def _categoriser_produits(env):
    """Amorce la famille d'approvisionnement sur les catégories connues."""
    Categorie = env['product.category']
    total = 0
    for famille, noms in CATEGORIES_CONNUES.items():
        for nom in noms:
            categories = Categorie.search([
                '|',
                ('complete_name', '=ilike', nom),
                ('name', '=ilike', nom),
                ('fma_famille_appro', '=', False),
            ])
            if categories:
                categories.write({'fma_famille_appro': famille})
                total += len(categories)
    _logger.info(
        "Ordonnancement FMA : %s catégorie(s) de produit rattachée(s) à une "
        "famille. Les autres familles (profilé, panneaux, complémentaire) "
        "restent à renseigner dans Configuration > Catégories de produits.",
        total,
    )


def _recalcul_initial(env):
    """Premier calcul sur les OF ouverts."""
    env['mrp.production']._cron_fma_recalcul_ordonnancement()


def post_init_hook(env):
    _typer_postes_de_charge(env)
    _categoriser_produits(env)
    _recalcul_initial(env)
