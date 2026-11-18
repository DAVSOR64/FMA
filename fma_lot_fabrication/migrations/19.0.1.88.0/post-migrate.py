"""Recalcule « A lotir » et « Menuiserie » : la regle se dedouble.

Un seul drapeau disait deux choses — appartenir au lot, et etre une
menuiserie. Le metier a releve la confusion : un habillage se debite AVEC
le lot, a la meme date, et l'ecarter lui retirait son debit. Il revient
donc dans le lot, sans numero de serie ni casier.

Les deux champs sont CALCULES ET STOCKES : Odoo ne rejoue pas leur calcul
sur les lignes deja en base. On s'en tient aux commandes vivantes — une
commande livree ne sera plus lotie, et rejouer tout l'historique couterait
des minutes de build pour rien.
"""
import logging

_logger = logging.getLogger(__name__)

TAILLE_LOT = 2000


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api
    env = api.Environment(cr, SUPERUSER_ID, {})
    Ligne = env["sale.order.line"]
    lignes = Ligne.search([
        ("order_id.state", "not in", ("done", "cancel")),
        ("display_type", "=", False),
        ("product_id", "!=", False),
    ])
    if not lignes:
        return
    champs = [Ligne._fields[n] for n in ("is_lotable", "fma_est_menuiserie")]
    for debut in range(0, len(lignes), TAILLE_LOT):
        paquet = lignes[debut:debut + TAILLE_LOT]
        for champ in champs:
            env.add_to_compute(champ, paquet)
        env.flush_all()
        env.invalidate_all()
    _logger.info(
        "fma_lot_fabrication : « A lotir » et « Menuiserie » recalcules sur "
        "%s ligne(s)", len(lignes))
