def migrate(cr, version):
    """Rebranche les collectes de composants sur leurs ordres de fabrication.

    En v19, le lien OF <-> transfert passe par ``production_group_id``, porte
    a la fois par ``mrp_production`` et par ``stock_move``. La migration v19 a
    rempli ce champ sur les OF, mais pas sur les mouvements deja en base :
    228 OF actifs sur 235 n'affichaient donc plus leur collecte, alors que le
    transfert existait, dans le bon etat, et que l'inventaire etait juste.
    Seule la navigation depuis l'OF etait rompue.

    Le rapprochement se fait par ``stock_picking.origin``, qui porte le NOM DE
    L'OF sur une collecte de composants — verifie sur la base : zero origine
    partagee par deux OF, le rapprochement est donc sans ambiguite.

    Deux limites volontaires :

    * seuls les OF actifs sont traites — sur un OF termine, le bouton
      n'apporte rien et ne justifie pas d'ecrire dans stock_move ;
    * seuls les mouvements dont le groupe est VIDE sont remplis, jamais
      ceux qui en portent deja un.
    """
    cr.execute(
        """
        UPDATE stock_move sm
        SET    production_group_id = mp.production_group_id
        FROM   stock_picking sp
        JOIN   stock_picking_type t ON t.id = sp.picking_type_id
        JOIN   mrp_production mp ON mp.name = sp.origin
        WHERE  sm.picking_id = sp.id
          AND  t.code = 'internal'
          AND  mp.state NOT IN ('done', 'cancel')
          AND  mp.production_group_id IS NOT NULL
          AND  sm.production_group_id IS NULL
        """
    )
    rebranches = cr.rowcount
    if not rebranches:
        return

    cr.execute(
        """
        SELECT count(*)
        FROM   mrp_production mp
        WHERE  mp.state NOT IN ('done', 'cancel')
          AND  NOT EXISTS (
                   SELECT 1 FROM stock_move sm
                   WHERE  sm.production_group_id = mp.production_group_id
                     AND  sm.picking_id IS NOT NULL)
        """
    )
    restants = cr.fetchone()[0]

    cr.execute(
        "INSERT INTO ir_logging"
        " (name, type, level, message, path, line, func, dbname, create_date)"
        " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(), now())",
        ("mrp_capacity_planning",
         f"Migration 19.0.1.0.10: {rebranches} mouvement(s) de collecte "
         f"rebranche(s) sur leur OF ; {restants} OF actif(s) restent sans "
         f"transfert visible",
         __file__, "0", "migrate"),
    )
