# -*- coding: utf-8 -*-
"""Désigne l'acheteur de chaque atelier, pour les achats nés de l'appro.

Les bons d'achat que l'approvisionnement fabrique — ceux des besoins MTO —
partaient tous au même acheteur, celui que la société désigne par défaut.
Les deux ateliers n'achètent pas par la même main : une affaire étiquetée
FMA relève des méthodes FMA-F2M, une affaire F2M de l'acheteur de La
Remaudière.

La règle est portée par `fma_custom/models/purchase_order.py`
(`_fma_acheteur_par_etiquette`), et lit deux champs de société. Cette
migration les renseigne, pour que la règle s'applique sans attendre une
visite dans les paramètres. Un champ déjà renseigné n'est pas touché : ce
serait défaire un choix fait à l'écran.

Les utilisateurs sont retrouvés par leur NOM, faute d'identifiant externe :
ce sont des comptes créés à l'usage, pas des données de module. La recherche
est tolérante — nom exact d'abord, puis fragment — et si elle ne trouve
rien, elle le dit dans le journal plutôt que de laisser le champ vide en
silence.
"""
from odoo import api, SUPERUSER_ID

#: Champ de société -> (nom attendu, fragment de repli).
ACHETEURS = {
    "fma_acheteur_fma_id": ("Méthodes FMA-F2M", "FMA-F2M"),
    "fma_acheteur_f2m_id": ("Freddy LE LUBOIS", "LUBOIS"),
}


def _journal(cr, message):
    cr.execute(
        "INSERT INTO ir_logging"
        " (name, type, level, message, path, line, func, dbname, create_date)"
        " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(), now())",
        ("fma_custom", message, __file__, "0", "migrate"),
    )


def _utilisateur(env, nom, fragment):
    Utilisateur = env["res.users"]
    trouve = Utilisateur.search([("name", "=", nom)], limit=2)
    if len(trouve) == 1:
        return trouve
    # Plusieurs homonymes : on ne tranche pas à sa place.
    if len(trouve) > 1:
        return Utilisateur
    trouve = Utilisateur.search([("name", "ilike", fragment)], limit=2)
    return trouve if len(trouve) == 1 else Utilisateur


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    societes = env["res.company"].search([])
    for champ, (nom, fragment) in ACHETEURS.items():
        utilisateur = _utilisateur(env, nom, fragment)
        if not utilisateur:
            _journal(
                cr,
                "Migration 19.0.1.8.0 : aucun utilisateur unique pour « %s »"
                " — le champ %s reste vide, à renseigner dans Achats >"
                " Configuration." % (nom, champ),
            )
            continue
        a_poser = societes.filtered(lambda s: not s[champ])
        if not a_poser:
            continue
        a_poser.write({champ: utilisateur.id})
        _journal(
            cr,
            "Migration 19.0.1.8.0 : %s = %s (id %s) sur %s société(s)"
            % (champ, utilisateur.name, utilisateur.id, len(a_poser)),
        )
