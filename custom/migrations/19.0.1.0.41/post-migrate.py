def migrate(cr, version):
    """Vide commercial_id sur les factures existantes.

    account.move.commercial_id est un champ calculé stocké : à sa création,
    Odoo l'a rempli sur **toutes** les factures, avec le commercial *actuel*
    du client — pas celui du moment de la vente. Mesuré sur la staging :
    5 162 factures sur 5 347, remontant à 2019.

    Or le PDF de facture affiche commercial_id en priorité. Sans ce nettoyage,
    réimprimer une facture ancienne afficherait un commercial différent de
    celui imprimé à l'époque, ce qui est inacceptable sur un document client.

    On ne peut pas régler ça en inversant la priorité dans le rapport :
    inv_commercial est un related vers le client, donc toujours renseigné —
    les nouvelles factures ne basculeraient jamais sur le nouveau champ.

    Après ce nettoyage, seules les factures issues d'une commande portent
    commercial_id, alimenté par sale.order._prepare_invoice. Les anciennes
    retombent sur inv_commercial, et leur PDF est identique à l'origine.

    Ce script s'exécute une fois par environnement, juste après la création
    de la colonne : à ce moment-là, aucune facture « nouvelle » n'existe
    encore, l'effacement est donc sans perte.
    """
    cr.execute(
        "UPDATE account_move SET commercial_id = NULL WHERE commercial_id IS NOT NULL"
    )
    nettoyees = cr.rowcount
    if not nettoyees:
        return

    cr.execute(
        "INSERT INTO ir_logging"
        " (name, type, level, message, path, line, func, dbname, create_date)"
        " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(), now())",
        ("custom",
         f"Migration 19.0.1.0.41: commercial_id vidé sur {nettoyees} facture(s) "
         f"antérieures, pour que leur PDF conserve le commercial d'origine",
         __file__, "0", "migrate"),
    )
