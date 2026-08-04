# -*- coding: utf-8 -*-
{
    "name": "FMA Atelier",
    "version": "17.0.1.0.0",
    "category": "Manufacturing",
    "summary": "Gestion des ateliers de production FMA",
    "description": """
Module socle pour gérer une notion métier d'atelier dans Odoo.

Objectifs :
- Créer un référentiel Atelier indépendant des entrepôts et emplacements.
- Ajouter l'atelier sur les ordres de fabrication.
- Permettre aux autres modules FMA, macro-planning et capacité, de dépendre proprement de ce module.
""",
    "author": "FMA / JBS",
    "website": "",
    "license": "LGPL-3",
    "depends": [
        "base",
        "mail",
        "mrp",
        "resource",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/fma_atelier_data.xml",
        "views/fma_atelier_views.xml",
        "views/mrp_production_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
