"""Recalcule l'ordonnancement : le denominateur et la colonne des declares.

« Assemblages planifies » ne comptait que les ordres restant a faire :
declarer une menuiserie sur huit faisait tomber la colonne de « 8 / 8 » a
« 0 / 7 ». Le total maigrissait a chaque declaration, et un lot entierement
fabrique finissait a « - ».

Une colonne « Menuiseries declarees » vient a cote, qui dit l'avancement de
fabrication — « 1 / 8 » des la premiere declaration.

Les deux champs sont STOCKES : changer leur calcul ne touche pas une seule
ligne deja ecrite. Le cron d'ordonnancement, lui, ne reprend que les lots
dont il reste quelque chose a fabriquer — les lots termines garderaient
leur ancienne valeur pour toujours. On force donc le recalcul ici, sur
tous les lots.
"""
import logging

_logger = logging.getLogger(__name__)

CHAMPS = ("ordo_assemblages_planifies", "ordo_assemblages_declares",
          "ordo_tout_planifie")


def migrate(cr, version):
    from odoo import SUPERUSER_ID, api
    env = api.Environment(cr, SUPERUSER_ID, {})
    Lot = env["fma.lot.fabrication"]
    lots = Lot.search([])
    if not lots:
        return
    for nom in CHAMPS:
        champ = Lot._fields.get(nom)
        if champ is not None:
            env.add_to_compute(champ, lots)
    env.flush_all()
    _logger.info(
        "fma_lot_fabrication : ordonnancement recalcule sur %s lot(s).",
        len(lots))
