# -*- coding: utf-8 -*-
"""Plafond de menuiseries par lot : 10 -> 8 sur les societes qui l'ont subi.

Changer la valeur par defaut d'un champ ne touche QUE les enregistrements
crees ensuite. Les societes existantes garderaient 10 indefiniment, et le
chiffre affiche a la mise en lot continuerait de mentir.

On ne reecrit que celles restees a 10, l'ancien defaut. Une societe reglee a
la main sur une autre valeur a fait un choix : le remplacer serait defaire
son travail sans le lui dire.
"""
import logging

_logger = logging.getLogger(__name__)

ANCIEN_DEFAUT = 10
NOUVEAU_DEFAUT = 8


def migrate(cr, version):
    cr.execute(
        """SELECT 1 FROM information_schema.columns
            WHERE table_name = 'res_company'
              AND column_name = 'fma_lot_max_menuiserie'"""
    )
    if not cr.fetchone():
        _logger.info("Plafond de lot : colonne absente, reprise sans objet")
        return

    cr.execute(
        "UPDATE res_company SET fma_lot_max_menuiserie = %s"
        " WHERE fma_lot_max_menuiserie = %s",
        (NOUVEAU_DEFAUT, ANCIEN_DEFAUT),
    )
    _logger.info(
        "Plafond de lot : %s societe(s) passee(s) de %s a %s menuiseries",
        cr.rowcount, ANCIEN_DEFAUT, NOUVEAU_DEFAUT)

    cr.execute(
        "SELECT name, fma_lot_max_menuiserie FROM res_company"
        " WHERE fma_lot_max_menuiserie NOT IN (%s, 0)"
        " ORDER BY name",
        (NOUVEAU_DEFAUT,),
    )
    autres = cr.fetchall()
    if autres:
        _logger.warning(
            "Plafond de lot : %s societe(s) gardent une valeur propre, non "
            "modifiee :", len(autres))
        for nom, valeur in autres:
            _logger.warning("   %-30s %s", nom, valeur)
