# Un code affaire commence par A, deux chiffres d'annee, deux de mois, puis
# un compteur : « A24-04-01435 ». Ce qui suit — un suffixe « /1 », un libelle,
# un separateur — n'en fait pas partie et n'est donc pas capture.
MOTIF_CODE = "^A[0-9]{2}-[0-9]{2}-[0-9]+"


def migrate(cr, version):
    """Isole le code affaire depuis le nom du projet.

    Le code etait ecrit a la main dans le nom : « A24-04-01435/1 -
    COULISSANTS COPRO ». De facon irreguliere, en plus — certains projets
    portent un suffixe, d'autres non, et ce suffixe ne designe pas la
    tranche : le projet cite ci-dessus porte six commandes a lui seul.

    En l'isolant dans son propre champ, la reference de tranche affichee sur
    les commandes (« A24-04-01435/2 ») devient calculable, et cesse de
    dependre de la facon dont le nom a ete saisi.

    Le nom du projet n'est pas touche : il reste ce que les metiers
    reconnaissent, et ce que le rapport de facture imprime aujourd'hui.

    Les projets dont le nom ne commence pas par un code affaire ne recoivent
    rien. Leurs commandes n'auront pas de reference de tranche, ce qui est
    preferable a une reference inventee.
    """
    cr.execute(
        "SELECT 1 FROM information_schema.columns"
        " WHERE table_name = 'project_project' AND column_name = 'x_code_affaire'"
    )
    if not cr.fetchone():
        return

    # Le nom est un champ traduisible, donc stocke en jsonb. On lit le
    # francais d'abord, l'anglais ensuite : les projets crees par la reprise
    # des affaires ne portent que la clef en_US.
    cr.execute(
        """
        UPDATE project_project
        SET    x_code_affaire = substring(
                   coalesce(name->>'fr_FR', name->>'en_US') from %s)
        WHERE  x_code_affaire IS NULL
          AND  coalesce(name->>'fr_FR', name->>'en_US') ~ %s
        """,
        (MOTIF_CODE, MOTIF_CODE),
    )
    codes = cr.rowcount

    cr.execute("SELECT count(*) FROM project_project WHERE x_code_affaire IS NULL")
    sans_code = cr.fetchone()[0]

    cr.execute(
        "INSERT INTO ir_logging"
        " (name, type, level, message, path, line, func, dbname, create_date)"
        " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(), now())",
        ("fma_sale_order_custom",
         f"Migration 19.0.1.0.28: code affaire isole sur {codes} projet(s) ; "
         f"{sans_code} projet(s) sans code, leurs commandes n'auront pas de "
         f"reference de tranche",
         __file__, "0", "migrate"),
    )
