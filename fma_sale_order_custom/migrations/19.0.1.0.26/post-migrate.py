def migrate(cr, version):
    """Bascule le projet du devis sur le champ natif project_id.

    Deux champs pointaient project.project depuis sale.order :

    - project_id, natif (sale_project), retenu en 19.0.1.0.3 comme
      remplacant d'analytic_account_id supprime en v19, et deja lu par
      mrp_capacity_planning et fma_mrp_dashboard ;
    - x_studio_projet, pose par Studio sous le libelle « Projet mtn », que
      le metier alimentait et que la reprise des affaires a rempli.

    Deux champs pour la meme notion, chacun lu par une moitie du systeme.
    On converge sur le natif : il porte le compte analytique du chantier,
    la navigation projet <-> commandes, et les modules de production le
    lisent deja.

    x_studio_projet n'est pas supprime. Sa colonne reste, l'export Power BI
    s'en sert encore en repli, et les vues cessent simplement de l'afficher.
    Sa suppression viendra quand plus rien ne le lira.

    En SQL et non par l'ORM, volontairement : ecrire project_id par l'ORM
    declencherait le recalcul de x_studio_bureau_dtude, dont le calcul
    vient d'etre rebranche sur project_id. Les projets crees depuis les
    affaires ont pour responsable l'utilisateur qui a lance la reprise ;
    le recalcul ecraserait donc les bureaux d'etude saisis.
    """
    cr.execute(
        "SELECT 1 FROM information_schema.columns"
        " WHERE table_name = 'sale_order' AND column_name = 'project_id'"
    )
    if not cr.fetchone():
        return

    cr.execute(
        """
        UPDATE sale_order
        SET    project_id = x_studio_projet
        WHERE  x_studio_projet IS NOT NULL
          AND  project_id IS NULL
        """
    )
    bascules = cr.rowcount

    # Divergences : les deux champs renseignes avec des projets differents.
    # On ne tranche pas a la place du metier, on compte et on trace.
    cr.execute(
        """
        SELECT count(*)
        FROM   sale_order
        WHERE  x_studio_projet IS NOT NULL
          AND  project_id IS NOT NULL
          AND  project_id <> x_studio_projet
        """
    )
    divergents = cr.fetchone()[0]

    cr.execute(
        "INSERT INTO ir_logging"
        " (name, type, level, message, path, line, func, dbname, create_date)"
        " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(), now())",
        ("fma_sale_order_custom",
         f"Migration 19.0.1.0.26: projet bascule sur project_id pour "
         f"{bascules} devis ; {divergents} devis ont deux projets differents "
         f"et n'ont pas ete touches",
         __file__, "0", "migrate"),
    )
