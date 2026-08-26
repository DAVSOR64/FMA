"""Detache des commandes les transferts internes, et repare la date de livraison.

`sale_id` est un champ calcule *stocke* : changer sa methode de calcul ne
recalcule pas les enregistrements existants. Les transferts internes deja
rattaches a une commande resteraient donc dans le bouton « Livraison », et les
commandes garderaient la date planifiee de ces transferts en date de livraison.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # 1. Un transfert interne (« Collecter les composants », transferts de
    #    fabrication) n'appartient pas a une commande de vente.
    cr.execute(
        """
        UPDATE stock_picking sp
           SET sale_id = NULL
          FROM stock_picking_type spt
         WHERE spt.id = sp.picking_type_id
           AND sp.sale_id IS NOT NULL
           AND spt.code NOT IN ('outgoing', 'incoming')
        """
    )
    _logger.info("Taux de service : %s transfert(s) interne(s) detache(s) de leur commande.", cr.rowcount)

    # 2. La date de livraison de la commande se lit sur la livraison client.
    #    On ne touche qu'aux commandes qui en ont une : ailleurs, la valeur a
    #    pu etre saisie a la main et on ne sait pas la refaire.
    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'sale_order'
           AND column_name = 'so_date_de_livraison_prevu'
        """
    )
    if not cr.fetchone():
        return

    cr.execute(
        """
        WITH livraison AS (
            SELECT sp.sale_id AS sale_id,
                   MIN(sp.scheduled_date) AS scheduled_date
              FROM stock_picking sp
              JOIN stock_picking_type spt ON spt.id = sp.picking_type_id
             WHERE sp.sale_id IS NOT NULL
               AND spt.code = 'outgoing'
               AND sp.state <> 'cancel'
               AND sp.scheduled_date IS NOT NULL
             GROUP BY sp.sale_id
        )
        UPDATE sale_order so
           SET so_date_de_livraison_prevu = livraison.scheduled_date::date
          FROM livraison
         WHERE livraison.sale_id = so.id
           AND so.so_date_de_livraison_prevu IS DISTINCT FROM livraison.scheduled_date::date
        """
    )
    _logger.info("Taux de service : date de livraison reprise sur la livraison client pour %s commande(s).", cr.rowcount)
