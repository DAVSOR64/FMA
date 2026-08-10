def migrate(cr, version):
    """Renseigne commercial_id sur les factures qui n'en ont pas.

    Ce script revient sur l'effet de la migration 19.0.1.0.41, qui avait vide
    commercial_id sur toutes les factures. Ce n'est pas une contradiction, et
    la raison merite d'etre ecrite noir sur blanc.

    19.0.1.0.41 partait d'une crainte : que la reimpression d'une facture
    ancienne affiche un commercial different de celui imprime a l'epoque. Cette
    crainte reposait sur une erreur d'analyse. Le rapport n'a jamais imprime de
    commercial fige : il lisait inv_commercial, qui est un **related** vers
    res_partner.part_commercial. Une facture de 2019 reimprimee aujourd'hui a
    toujours porte le commercial *actuel* du client, jamais celui de 2019.

    Remplir commercial_id depuis res_partner.x_studio_commercial_1 reproduit
    donc exactement ce que le PDF sort aujourd'hui, a une reserve pres traitee
    ci-dessous. Et cela apporte ce que le related ne donnait pas : a partir de
    maintenant, la valeur est **figee**. Changer le commercial d'un client ne
    reecrira plus le commercial de ses factures passees.

    La reserve : pour les clients dont l'employe rattache diverge du texte
    part_commercial (691 cas mesures sur la staging), le nom imprime changera.
    C'est assume — la regle posee par le metier est que le Many2one fait foi et
    que l'orthographe vient de la fiche employe. La requete de controle donnee
    avec ce script chiffre l'impact exact avant deploiement.

    Aucun effet sur Power BI : l'export des factures ne comporte pas de colonne
    commercial. Il ne la porte que sur les clients et sur les devis.

    On ne touche qu'aux factures dont commercial_id est vide : celles issues
    d'une commande le tiennent deja de sale.order._prepare_invoice, et cette
    valeur-la est la bonne — c'est le commercial de la vente, pas celui du
    client d'aujourd'hui.
    """
    cr.execute(
        """
        UPDATE account_move m
        SET    commercial_id = p.x_studio_commercial_1
        FROM   res_partner p
        WHERE  p.id = m.partner_id
          AND  m.commercial_id IS NULL
          AND  p.x_studio_commercial_1 IS NOT NULL
        """
    )
    remplies = cr.rowcount
    if not remplies:
        return

    cr.execute(
        "INSERT INTO ir_logging"
        " (name, type, level, message, path, line, func, dbname, create_date)"
        " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(), now())",
        ("custom",
         f"Migration 19.0.1.0.47: commercial_id renseigne sur {remplies} "
         f"facture(s) depuis le commercial du client",
         __file__, "0", "migrate"),
    )
