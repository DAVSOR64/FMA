"""Recalcule « A lotir » : la definition d'une menuiserie a encore change.

Le critere passe de la position du repere aux DIMENSIONS. LOGIKAL donne
une position aux « Position matiere » comme aux menuiseries : la premiere
version de ce correctif ne les ecartait donc pas.

``is_lotable`` est un champ CALCULE ET STOCKE. Odoo ne rejoue pas le calcul
des lignes deja en base quand la formule change : sans cette migration, les
fournitures resteraient eligibles au lotissement sur toutes les commandes
existantes, et seules les nouvelles beneficieraient de la correction.

On se limite aux commandes encore vivantes. Une commande livree et facturee
ne sera plus lotie, et rejouer le calcul sur tout l'historique couterait des
minutes de build pour un resultat que personne ne lira.
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
    champ = Ligne._fields["is_lotable"]
    for debut in range(0, len(lignes), TAILLE_LOT):
        paquet = lignes[debut:debut + TAILLE_LOT]
        env.add_to_compute(champ, paquet)
        env.flush_all()
        env.invalidate_all()
    _logger.info(
        "fma_lot_fabrication : « A lotir » recalcule sur %s ligne(s)",
        len(lignes))
