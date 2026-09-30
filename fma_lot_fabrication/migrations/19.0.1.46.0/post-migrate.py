# -*- coding: utf-8 -*-
"""« Date planifiee » du lot : la caler sur le debut de son OF de debit.

Le champ existait deja, rempli a la creation du lot avec l'heure du moment.
Il devient calcule depuis l'OF de debit, mais Odoo ne calcule un champ stocke
que sur les lignes dont la COLONNE vient d'etre creee. Celle-ci existe : sans
cette reprise, les lots deja en base garderaient leur horodatage de creation,
et seuls les nouveaux diraient vrai.

Un lot peut porter plusieurs ordres de debit si l'un a ete annule puis
regenere. DISTINCT ON retient le plus recent non annule, qui est celui que le
calcul retiendrait aussi.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    for table, colonne in (("fma_lot_fabrication", "date_planned_start"),
                           ("mrp_production", "lot_production_type")):
        cr.execute(
            """SELECT 1 FROM information_schema.columns
                WHERE table_name = %s AND column_name = %s""",
            (table, colonne),
        )
        if not cr.fetchone():
            _logger.info(
                "Date planifiee : %s.%s absent, reprise sans objet",
                table, colonne)
            return

    cr.execute(
        """UPDATE fma_lot_fabrication l
              SET date_planned_start = d.date_start
             FROM (
                 SELECT DISTINCT ON (lot_fabrication_id)
                        lot_fabrication_id, date_start
                   FROM mrp_production
                  WHERE lot_fabrication_id IS NOT NULL
                    AND lot_production_type = 'debit'
                    AND state <> 'cancel'
                    AND date_start IS NOT NULL
                  ORDER BY lot_fabrication_id, id DESC
             ) d
            WHERE d.lot_fabrication_id = l.id
              AND l.date_planned_start IS DISTINCT FROM d.date_start"""
    )
    _logger.info(
        "Date planifiee : %s lot(s) cale(s) sur le debut de leur debit",
        cr.rowcount)

    cr.execute(
        """SELECT COUNT(*) FROM fma_lot_fabrication l
            WHERE NOT EXISTS (
                SELECT 1 FROM mrp_production d
                 WHERE d.lot_fabrication_id = l.id
                   AND d.lot_production_type = 'debit'
                   AND d.state <> 'cancel')"""
    )
    reste = cr.fetchone()[0]
    if reste:
        _logger.info(
            "Date planifiee : %s lot(s) sans ordre de debit gardent leur date "
            "de mise en lot — ils la prendront a la generation des ordres.",
            reste)
