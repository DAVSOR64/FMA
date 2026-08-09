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
    "version": "19.0.1.0.9",
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
