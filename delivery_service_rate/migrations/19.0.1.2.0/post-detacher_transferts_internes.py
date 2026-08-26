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
    #    On ne touche qu'aux commandes qui en ont une ; le cas « aucune
    #    livraison » est traite en 3.
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
            -- MAX et non MIN : une commande peut porter plusieurs
            -- livraisons -- les commandes deja confirmees gardent les deux BL
            -- que le regroupement evite desormais, et une affaire peut
            -- s'expedier en plusieurs fois. Elle n'est livree qu'au dernier
            -- BL. MIN aurait de plus tire le retroplanning vers l'amont :
            -- so_date_de_livraison_prevu est la premiere source de date de
            -- livraison pour la planification des OF.
            SELECT sp.sale_id AS sale_id,
                   MAX(sp.scheduled_date) AS scheduled_date
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

    # 3. Restent les commandes polluees qui n'ont aucune livraison client a
    #    lire -- BL annule, ou commande dont la chaine s'arrete a la
    #    fabrication. Leur date vient d'un transfert interne : on ne la
    #    reconnait qu'a ca, et on ne la remplace que dans ce cas, pour ne pas
    #    ecraser une date saisie a la main. La valeur de repli est la date
    #    promise (BPE + delai), celle-la meme dont _compute_so_date_de_livraison
    #    initialise les deux champs.
    #
    #    Le rapprochement se fait sur `origin` et non sur sale_id : l'etape 1
    #    vient justement de detacher ces transferts de leur commande.
    cr.execute(
        """
        UPDATE sale_order so
           SET so_date_de_livraison_prevu = so.so_date_de_livraison
         WHERE so.so_date_de_livraison IS NOT NULL
           AND so.so_date_de_livraison_prevu IS DISTINCT FROM so.so_date_de_livraison
           AND NOT EXISTS (
                 SELECT 1
                   FROM stock_picking sp
                   JOIN stock_picking_type spt ON spt.id = sp.picking_type_id
                  WHERE sp.sale_id = so.id
                    AND spt.code = 'outgoing'
                    AND sp.state <> 'cancel'
           )
           AND EXISTS (
                 SELECT 1
                   FROM stock_picking sp
                   JOIN stock_picking_type spt ON spt.id = sp.picking_type_id
                  WHERE sp.origin = so.name
                    AND spt.code NOT IN ('outgoing', 'incoming')
                    AND sp.scheduled_date::date = so.so_date_de_livraison_prevu
           )
        """
    )
    _logger.info(
        "Taux de service : date de livraison rendue a la date promise pour %s commande(s) sans BL client.",
        cr.rowcount,
    )
