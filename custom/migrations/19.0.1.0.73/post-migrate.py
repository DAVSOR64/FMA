# -*- coding: utf-8 -*-
"""Force le recalcul de « Projet de la vente » sur les OF et les transferts.

Un champ calcule et STOCKE n'est recalcule par Odoo qu'a la creation de sa
colonne. Changer ensuite la methode de calcul ne touche pas une seule ligne
existante : la valeur ecrite le premier jour reste, meme fausse.

C'est ce qui s'est passe ici. La colonne des transferts a ete creee alors que
le calcul ne lisait que sale_id : toutes les livraisons ont recu leur projet,
tous les transferts d'ordre de fabrication ont recu du vide. Les trois
corrections suivantes ont bien change la methode, sans jamais rejouer le
calcul — d'ou un champ obstinement vide malgre un code juste.

Les ordres de fabrication sont traites d'abord : le transfert lit le projet de
son OF, un OF encore vide donnerait un transfert vide.

Par lots, avec vidage intermediaire : la production compte des dizaines de
milliers de transferts, et tout recalculer d'un bloc tiendrait la transaction
ouverte trop longtemps.
"""
from odoo import api, SUPERUSER_ID

#: Nombre d'enregistrements recalcules avant chaque vidage.
TAILLE_LOT = 2000


def _recalculer(env, modele, journal):
    """Marque le champ a recalculer sur tous les enregistrements du modele."""
    Modele = env[modele]
    champ = Modele._fields.get("x_studio_projet_de_la_vente")
    if champ is None:
        return 0

    ids = Modele.with_context(active_test=False).search([]).ids
    for debut in range(0, len(ids), TAILLE_LOT):
        lot = Modele.browse(ids[debut:debut + TAILLE_LOT])
        env.add_to_compute(champ, lot)
        env.flush_all()
        env.invalidate_all()
    journal.append("%s : %s enregistrement(s)" % (modele, len(ids)))
    return len(ids)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    journal = []
    # L'OF d'abord : le transfert lit le projet de l'OF.
    _recalculer(env, "mrp.production", journal)
    _recalculer(env, "stock.picking", journal)

    cr.execute(
        "INSERT INTO ir_logging"
        " (name, type, level, message, path, line, func, dbname, create_date)"
        " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(), now())",
        ("custom",
         "Migration 19.0.1.0.60 : recalcul de x_studio_projet_de_la_vente — %s"
         % (", ".join(journal) or "aucun modele concerne"),
         __file__, "0", "migrate"),
    )
