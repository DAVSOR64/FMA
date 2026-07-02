# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "FMA: Studio Models",
    "summary": "Business models migrated from Odoo Studio (schema + views + security)",
    "description": """
        Real Odoo models replacing the "manual" models that Odoo Studio
        created directly in the database (module studio_customization):
        Affaire, Capacité par poste, Délai entre opérations, Gamme/Série
        maintenance, Règlements, Remises, and small PO/AM line extensions.

        Technical names (x_*) are kept identical to the Studio-generated
        ones on purpose, so that:
        - existing data (same tables) keeps working with no migration,
        - other modules already doing env['x_affaire'] / env['x_capacite_par_poste']
          (mrp_capacity_planning, sqlite_connector) keep working unchanged.

        See STUDIO_AUDIT.md at the repo root for the full audit and the
        rationale behind this module.
    """,
    "author": "Odoo PS",
    "version": "19.0.1.0.0",
    "depends": ["base", "mail", "mrp", "purchase", "account"],
    "data": [
        "security/ir.model.access.csv",
        "views/x_affaire_views.xml",
        "views/x_capacite_par_poste_views.xml",
        "views/x_delai_entre_operatio_views.xml",
        "views/x_gamme_serie_mtn_views.xml",
        "views/x_reglements_views.xml",
        "views/x_remise_views.xml",
        "views/x_lines_views.xml",
        "views/menus.xml",
    ],
    "license": "LGPL-3",
}
