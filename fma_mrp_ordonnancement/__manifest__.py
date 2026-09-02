# -*- coding: utf-8 -*-
{
    'name': "FMA - Ordonnancement & Scores",
    'version': '19.0.2.9.5',
    'category': 'Manufacturing',
    'summary': "Reprise du fichier « Ordre de production FMA » : complexité, "
               "heures par poste, scores et suivi des approvisionnements sur l'OF",
    'description': """
Remplace le classeur Excel « Ordre de production FMA - Copie.xlsm ».

Principe : chaque colonne de l'onglet TDB_SAISIE devient un champ sur
mrp.production, calculé et stocké, donc filtrable, groupable et utilisable
en pivot. Les onglets import_odoo / of 26 stock / ORDRE_TRAVAIL / PO,
qui étaient des exports Odoo collés à la main, disparaissent.

Apports :
- Typage métier des postes de charge (Débit, CU banc, Usinage, Montage,
  Vitrage, Emballage) pour ne plus dépendre du libellé exact.
- Heures prévues par poste sur l'OF, issues des ordres de travail.
- Nombre de repères et score de complexité, calculés depuis le champ
  existant x_studio_niveau_de_complexite (format « A*3 » sur plusieurs lignes).
- Barèmes heures/repère -> score, paramétrables (onglet SEQUENCAGE).
- Référentiel gammiste x typologie -> niveau de complexité (onglet SEQUENCAGE).
- Dates d'arrivée et statuts de réception par famille d'approvisionnement
  (profilé, vitrage, panneaux, complémentaire), sans découpage de texte.
- Déclencheurs de recalcul côté achat, réception, barème et poste de charge,
  plus un cron de rattrapage nocturne.
""",
    'author': 'Paxo Consulting',
    'license': 'LGPL-3',
    'depends': [
        'mrp',
        'stock',
        'purchase_stock',
        'sale_mrp',
        'fma_atelier',
        'mrp_capacity_planning',
        'product_subfamily',
        'custom',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/fma_complexite_niveau_data.xml',
        'data/fma_complexite_regle_data.xml',
        'data/fma_bareme_score_data.xml',
        'data/cron.xml',
        'views/mrp_workcenter_views.xml',
        'views/fma_complexite_views.xml',
        'views/fma_bareme_score_views.xml',
        'views/product_views.xml',
        'views/purchase_order_line_views.xml',
        'views/mrp_production_views.xml',
        'views/menu.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
