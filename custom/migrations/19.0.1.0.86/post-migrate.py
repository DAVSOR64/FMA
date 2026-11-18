# -*- coding: utf-8 -*-
"""Remises ALU et ACIER a 47 % sur toutes les societes existantes.

47 % est le taux applique aujourd'hui a tous les clients societe. Les
colonnes viennent d'etre creees vides : on les initialise.

SQL direct et non ORM : aucune ecriture ne declenche d'envoi vers IziQo pour
des milliers de fiches d'un coup. La prochaine synchronisation planifiee
reprendra les valeurs.

Seules les valeurs vides ou nulles sont touchees : le script se rejoue sans
ecraser une remise saisie.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    journal = []
    for colonne in ("fma_remise_alu", "fma_remise_acier"):
        cr.execute(
            "UPDATE res_partner SET %s = 47.0"
            " WHERE is_company AND (%s IS NULL OR %s = 0)" % (colonne, colonne, colonne))
        journal.append("%s : %d societe(s)" % (colonne, cr.rowcount))
    _logger.info("Remises client initialisees a 47 %% — %s", ", ".join(journal))
