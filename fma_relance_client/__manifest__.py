# -*- coding: utf-8 -*-
{
    "name": "FMA - Relance client depuis les factures",
    "summary": "Vendeur, commercial et projet sur la liste des factures, "
               "et relance du client sur une selection",
    "version": "19.0.1.0.0",
    "depends": [
        # commercial_id, le commercial FMA recopie depuis la commande.
        "custom",
        # sale.order.project_id : le projet n'existe pas sur la facture, il se
        # remonte depuis la commande a l'origine des lignes.
        "sale_project",
    ],
    "data": [
        "views/account_move_views.xml",
    ],
    "installable": True,
    "license": "LGPL-3",
}
