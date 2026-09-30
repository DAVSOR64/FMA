# -*- coding: utf-8 -*-
"""« Livraison reelle le » change de source : reprise de l'existant.

Le champ portait la DATE EFFECTIVE du dernier bon de livraison, et n'etait
rempli qu'une fois tous les bons faits. Il porte desormais la DATE PLANIFIEE
du bon le plus tardif, faite ou non.

Le choix se justifie par l'usage : on veut savoir quand la commande part, et
le savoir AVANT qu'elle parte. Une date effective n'existe qu'apres coup,
donc elle ne repond jamais quand on a besoin de la reponse. Et un bon valide
qui laisse un reliquat n'a pas livre la commande : c'est la date du reliquat
qui dit quand elle le sera.

Sans reprise, le champ garderait indefiniment l'ancienne valeur sur les
commandes deja livrees, et n'en aurait aucune sur celles en cours -- soit
exactement l'inverse de ce qu'on attend de lui. On le recalcule donc sur
toute la base, et on journalise le nombre de commandes qui changent.

Le nouveau declencheur, lui, ne vaut que pour l'avenir : il se declenche a
l'ecriture d'une date planifiee.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """SELECT 1 FROM information_schema.columns
            WHERE table_name = 'sale_order'
              AND column_name = 'so_date_livraison_reelle'"""
    )
    if not cr.fetchone():
        _logger.info("Livraison reelle : colonne absente, reprise sans objet")
        return

    # La plus tardive des dates planifiees des bons SORTANTS non annules.
    # Le filtre sur le sens est essentiel : un transfert de composants, que le
    # macro planning deplace vers l'amont, donnerait a la commande une date de
    # fabrication en guise de date de livraison. Le piege a deja coute une
    # livraison promise en octobre 2026 tombee au 12 decembre 2025.
    cr.execute(
        """UPDATE sale_order so
              SET so_date_livraison_reelle = derniere.jour
             FROM (
                 SELECT sp.sale_id AS so_id,
                        MAX(sp.scheduled_date)::date AS jour
                   FROM stock_picking sp
                   JOIN stock_picking_type spt ON spt.id = sp.picking_type_id
                  WHERE sp.sale_id IS NOT NULL
                    AND sp.state <> 'cancel'
                    AND spt.code = 'outgoing'
                    AND sp.scheduled_date IS NOT NULL
                  GROUP BY sp.sale_id
             ) derniere
            WHERE so.id = derniere.so_id
              AND so.so_date_livraison_reelle IS DISTINCT FROM derniere.jour"""
    )
    _logger.info(
        "Livraison reelle : %s commande(s) redatees depuis leurs bons de "
        "livraison", cr.rowcount)

    # Les commandes sans aucun bon prennent la date prevue -- delai + BPE.
    # C'est ce que le magasin recevra quand le bon sera cree, Odoo calant sa
    # date planifiee sur l'engagement.
    cr.execute(
        """UPDATE sale_order so
              SET so_date_livraison_reelle = so.so_date_de_livraison
            WHERE so.so_date_de_livraison IS NOT NULL
              AND so.so_date_livraison_reelle IS DISTINCT FROM so.so_date_de_livraison
              AND NOT EXISTS (
                  SELECT 1 FROM stock_picking sp
                    JOIN stock_picking_type spt ON spt.id = sp.picking_type_id
                   WHERE sp.sale_id = so.id
                     AND sp.state <> 'cancel'
                     AND spt.code = 'outgoing'
                     AND sp.scheduled_date IS NOT NULL
              )"""
    )
    _logger.info(
        "Livraison reelle : %s commande(s) sans bon alignees sur la date "
        "prevue", cr.rowcount)

    # « Date de livraison prevue » (delai + BPE) et commitment_date doivent
    # dire la meme chose : c'est la regle posee, et le calcul la respecte
    # desormais. Mais il ne s'execute que si so_date_bpe ou le delai bouge.
    # Sur les commandes deja en base, ni l'un ni l'autre ne bougera : elles
    # garderaient une commitment_date d'avant, voire aucune, alors que la
    # replanification et le retroplanning la lisent en PREMIER. On l'aligne
    # donc ici, une fois, sur toute la base.
    #
    # commitment_date est un Datetime : le calcul y ecrit une date, qu'Odoo
    # pose a minuit. Le ::timestamp fait la meme chose.
    cr.execute(
        """SELECT so.name, so.commitment_date::date, so.so_date_de_livraison
             FROM sale_order so
            WHERE so.so_date_de_livraison IS NOT NULL
              AND so.commitment_date IS NOT NULL
              AND so.commitment_date::date
                  IS DISTINCT FROM so.so_date_de_livraison
            ORDER BY ABS(so.commitment_date::date - so.so_date_de_livraison)
                     DESC
            LIMIT 30"""
    )
    divergences = cr.fetchall()

    cr.execute(
        """UPDATE sale_order so
              SET commitment_date = so.so_date_de_livraison::timestamp
            WHERE so.so_date_de_livraison IS NOT NULL
              AND so.commitment_date IS DISTINCT FROM
                  so.so_date_de_livraison::timestamp"""
    )
    _logger.info(
        "Date d'engagement : %s commande(s) alignees sur la date de "
        "livraison prevue", cr.rowcount)

    if divergences:
        _logger.warning(
            "Les commandes ci-dessous portaient une date d'engagement "
            "differente de leur date prevue. Elle est desormais alignee ; "
            "si l'une d'elles etait un engagement client negocie a part, "
            "c'est ici qu'il faut le retablir a la main :")
        for nom, avant, apres in divergences:
            _logger.warning("  %-18s %s -> %s", nom, avant, apres)
