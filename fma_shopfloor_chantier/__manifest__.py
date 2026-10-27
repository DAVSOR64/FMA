# -*- coding: utf-8 -*-
{
    "name": "FMA Shop Floor Chantier",
    "version": "19.0.1.0.0",
    "category": "Manufacturing",
    "summary": "Afficher le chantier de l'affaire sur la carte de l'operateur connecte",
    "description": """
Le panneau des operateurs de l'Atelier montre, pour chaque personne
connectee, ses postes en cours et le temps pointe — mais pas l'affaire sur
laquelle elle travaille : la donnee ne remonte pas jusqu'au client.

Ce module la joint cote serveur, puis l'affiche sous le badge du poste.
Le chantier lu est « x_studio_projet_de_la_vente » de l'ordre de
fabrication, alimente depuis le projet de la commande.
""",
    "author": "FMA",
    "license": "LGPL-3",
    "depends": ["mrp_workorder"],
    "assets": {
        "web.assets_backend": [
            "fma_shopfloor_chantier/static/src/mrp_display/employees_panel_chantier.xml",
            "fma_shopfloor_chantier/static/src/mrp_display/employees_panel_chantier.scss",
        ],
    },
    "installable": True,
    "application": False,
}
