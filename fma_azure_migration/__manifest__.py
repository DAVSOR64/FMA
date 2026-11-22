# -*- coding: utf-8 -*-
{
    "name": "FMA Migration des pièces jointes vers Azure (jetable)",
    # 1.0.0 : la boucle de migration en methode, declenchee par une action
    # planifiee qui se desactive seule quand il ne reste plus rien.
    "version": "19.0.1.0.0",
    "category": "Tools",
    "summary": "Deplace l'historique des pieces jointes vers Azure, par "
               "paquets, sans surveillance",
    "description": """
Migration des pièces jointes vers Azure
=======================================

MODULE JETABLE. Il n'a qu'un travail : vider le filestore vers le stockage
Azure, par paquets, dans le worker cron — donc sans qu'un navigateur reste
ouvert. Une fois le filestore vide, l'action planifiee se desactive d'elle
meme et le module se desinstalle.

Voir README.md.
""",
    "author": "FMA",
    "license": "LGPL-3",
    # fs_attachment porte le stockage, la fiche fs.storage et la methode
    # _move_attachment_to_store qui fait le travail. Rien d'autre n'est
    # necessaire : ce module n'ajoute aucun champ et aucune vue.
    "depends": ["fs_attachment"],
    "data": ["data/ir_cron.xml"],
    "installable": True,
    "application": False,
    "auto_install": False,
}
