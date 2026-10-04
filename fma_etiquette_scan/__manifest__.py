# -*- coding: utf-8 -*-
{
    "name": "FMA Etiquettes, scan atelier et SAV",
    # 1.0.0 : etiquette par menuiserie (Code128 + QR), poste de scan pour la
    # declaration de fabrication, localisation et SAV au numero de serie.
    "version": "19.0.1.0.0",
    "category": "Manufacturing",
    "summary": "Une etiquette par menuiserie : declaration de fabrication au "
               "scan, localisation et SAV au numero de serie",
    "description": """
Etiquettes, scan et SAV par menuiserie
======================================

Le lot de fabrication cree un ordre et un numero de serie par menuiserie.
Ce module s'appuie sur ce numero, et sur lui seul :

* une **etiquette** 100 x 150 mm par menuiserie (code-barres Code128 du
  numero de serie, QR code de declaration SAV) ;
* un **poste de scan** — douchette USB ou PDA en mode clavier — pour
  declarer la fabrication menuiserie par menuiserie, localiser une
  menuiserie et ouvrir un ticket SAV ;
* le **SAV au numero de serie** : ticket d'assistance rattache a la
  menuiserie, a son ordre, a son lot et a sa commande.

Voir README.md.
""",
    "author": "FMA",
    "license": "LGPL-3",
    "depends": [
        # Porte le lot, la scission en un ordre par menuiserie et les numeros
        # de serie pre-affectes : tout ce que l'etiquette designe.
        "fma_lot_fabrication",
        "mrp",
        "stock",
        # Lecture d'un code-barres sans que le curseur soit dans un champ.
        "barcodes",
        # Deja tire par « custom ». Ni helpdesk_stock ni helpdesk_repair ne
        # sont installes chez FMA : le lien ticket -> numero de serie est
        # porte ici (fma_serial_id).
        "helpdesk",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_config_parameter.xml",
        "report/paperformat.xml",
        "report/etiquette_menuiserie.xml",
        "wizard/fma_poste_scan_views.xml",
        "views/stock_lot_views.xml",
        "views/mrp_production_views.xml",
        "views/fma_lot_fabrication_views.xml",
        "views/helpdesk_ticket_views.xml",
        "views/sav_templates.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
