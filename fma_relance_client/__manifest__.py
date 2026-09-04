# -*- coding: utf-8 -*-
{
    "name": "FMA - Relance client depuis les factures",
    "author": "FMA",
    "summary": "Vendeur, commercial et projet sur la liste des factures, "
               "et relance du client sur une selection",
    "version": "19.0.1.2.4",
    "depends": [
        # commercial_id, le commercial FMA recopie depuis la commande.
        "custom",
        # sale.order.project_id : le projet n'existe pas sur la facture, il se
        # remonte depuis la commande a l'origine des lignes.
        "sale_project",
    ],
    "data": [
        "data/ir_cron.xml",
        "views/account_move_views.xml",
    ],
    "installable": True,
    "license": "LGPL-3",
}
