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
    # 1.0.7 : le bouton « Validé » renseigne « Devis validé le », qui
    # alimente le taux de transformation du tableau de bord.
    # 1.0.8 : pose les champs de relance et le commentaire dans l'onglet
    # Chronologie cree par « custom ». Ils sont declares ici, et « custom »
    # ne peut pas dependre de ce module : il en est la dependance.
    # 1.0.9 : barre d'etat allegee, Pro forma et Annuler passent dans le
    # menu Action (actions serveur liees au modele).
    # 1.0.10 : portage des 4 derniers champs Studio de sale.order
    # (x_studio_avancement, x_studio_commercial_si_prospect,
    # x_studio_motif_annul, x_studio_commercial_client_mtn), definitions
    # relevees en base. Prealable indispensable a la refonte de la vue :
    # un champ « manual » n'existe pas au chargement des vues des modules.
    # 1.0.11 : x_studio_commercial_1 devient le reflet de commercial_id.
    "version": "19.0.1.0.37",
    "depends": [
        "sale_management",
        "custom",
        "fma_studio_models",
        "crm",
        "project",
        # Porte sale.order.project_id, le champ projet natif retenu en
        # 19.0.1.0.3 comme remplacant d'analytic_account_id (supprime en v19)
        # et deja lu par mrp_capacity_planning et fma_mrp_dashboard. Sans
        # cette dependance, nos vues ne peuvent pas le placer.
        "sale_project",
        "documents",
    ],
    "data": [
        "views/sale_order_views.xml",
        "views/project_project_views.xml",
    ],
    "license": "LGPL-3",
}
