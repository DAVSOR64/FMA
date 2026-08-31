# -*- coding: utf-8 -*-
"""Constantes partagées du module d'ordonnancement FMA."""

# Types de poste métier. Volontairement décorrélés du libellé du poste de
# charge : dans le classeur Excel, la colonne « Ordre de travail » vaut tantôt
# « Débit », tantôt « Débit FMA », ce qui rendait les XLOOKUP fragiles.
FMA_POSTE_TYPES = [
    ('debit', "Débit"),
    ('banc', "CU (banc)"),
    ('usinage', "Usinage"),
    ('montage', "Montage"),
    ('vitrage', "Vitrage"),
    ('emballage', "Emballage"),
]

FMA_POSTE_KEYS = [key for key, _label in FMA_POSTE_TYPES]

# Postes pour lesquels l'onglet SEQUENCAGE définit un barème heures/repère.
FMA_POSTES_SCORES = ['debit', 'banc', 'usinage', 'montage']

# Jetons de reconnaissance utilisés uniquement à l'installation, pour typer
# automatiquement les postes de charge existants. Même logique que
# mrp_capacity_planning._planning_operation_rank.
FMA_POSTE_TOKENS = [
    ('débit', 'debit'),
    ('debit', 'debit'),
    ('banc', 'banc'),
    ('cu', 'banc'),
    ('usinage', 'usinage'),
    ('montage', 'montage'),
    ('vitrage', 'vitrage'),
    ('emballage', 'emballage'),
]

FMA_CATEGORIES_APPRO = [
    ('profil', "Profilé"),
    ('vitrage', "Vitrage"),
    ('panneaux', "Panneaux"),
    ('complementaire', "Complémentaire"),
]

FMA_CATEGORIES_APPRO_KEYS = [key for key, _label in FMA_CATEGORIES_APPRO]

FMA_STATUT_RECEPTION = [
    ('none', "Aucune commande"),
    ('pending', "Non reçu"),
    ('partial', "Partiellement reçu"),
    ('full', "Entièrement reçu"),
]

# États d'un OF pour lequel plus aucun recalcul d'ordonnancement n'a de sens.
FMA_ETATS_CLOS = ('done', 'cancel')
