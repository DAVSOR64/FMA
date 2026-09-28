# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "Sale Order Customization",
    "description": """
            The purpose of this module is add a new state 'Devis Validé' between QUOTATION and SALES ORDER
            with a new action "Validation" and perform actions on its related fields on the sales order.
            Task: 4098688
        """,
    "author": "Odoo PS",
    # 1.0.9 : barre d'etat allegee, Pro forma et Annuler passent dans le
    # menu Action (actions serveur liees au modele).
    # 1.0.10 : portage des champs Studio x_studio_avancement,
    # x_studio_commercial_si_prospect et x_studio_motif_annul, definitions
    # relevees en base. Prealable a la refonte de la vue : un champ
    # « manual » n'existe pas au chargement des vues des modules.
    # 1.0.12 : les quatre paves de la maquette. Sans les notions de projet,
    # de chantier ni de tranche, qui restent sur Staging_19 — d'ou l'absence
    # de la dependance sale_project et de views/project_project_views.xml.
    # 1.0.19 : RAF HT devient un champ calcule et stocke, et il n'y en
    # a plus qu'un. Reprise des commandes deja en base en post-migrate.
    # 1.0.20 : RAF HT visible dans l'onglet Analyse Financiere, avec le
    # total HT et le facture HT qui le composent.
    "version": "19.0.1.0.20",
    "depends": [
        "sale_management",
        "custom",
        "fma_studio_models",
        "crm",
        "project",
        "documents",
    ],
    "data": ["views/sale_order_views.xml"],
    "license": "LGPL-3",
}
