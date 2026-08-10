from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Cree un projet pour chaque affaire qui n'en a pas encore.

    L'affaire etait un simple texte sur le devis (x_studio_ref_affaire).
    Elle devient un vrai projet, seul objet capable de porter l'analytique,
    le budget et le decoupage en tranches.

    Mesure sur la staging : 3 747 devis portent une affaire sans projet, pour
    3 327 affaires distinctes. Un projet est donc cree **par affaire**, pas
    par devis : les quelque 420 devis qui partagent une affaire sont
    rattaches au meme projet, ce qui est tout l'interet de la manoeuvre.

    Nom : « <numero du devis le plus ancien> - <affaire> ». Le numero rend le
    nom unique et situe l'affaire dans le temps ; deux affaires homonymes
    restent ainsi distinguables.

    On passe par l'ORM : creer un projet declenche la creation de son compte
    analytique et l'application des valeurs par defaut de la societe, ce qu'un
    INSERT direct raterait.

    Ce script vit dans fma_sale_order_custom et non dans custom : c'est ici
    qu'est declare x_studio_projet. Une migration de custom s'executerait
    avant le chargement de ce module, et le champ serait introuvable dans le
    registre. x_studio_ref_affaire, lui, vient de custom, dont ce module
    depend — il est donc bien visible.

    Idempotent : les devis deja rattaches a un projet ne sont pas repris, et
    une affaire dont le projet existe deja est simplement reliee.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})

    orders = env["sale.order"].search(
        [("x_studio_projet", "=", False), ("x_studio_ref_affaire", "!=", False)],
        order="date_order asc, id asc",
    )

    par_affaire = {}
    for order in orders:
        affaire = (order.x_studio_ref_affaire or "").strip()
        if affaire:
            # Les devis sont deja tries : le premier vu est le plus ancien.
            par_affaire.setdefault(affaire, env["sale.order"])
            par_affaire[affaire] |= order

    if not par_affaire:
        return

    Project = env["project.project"]
    crees = 0
    rattaches = 0

    for affaire, devis in par_affaire.items():
        premier = devis[0]
        nom = f"{premier.name} - {affaire}"[:255]

        projet = Project.search([("name", "=", nom)], limit=1)
        if not projet:
            vals = {
                "name": nom,
                "partner_id": premier.partner_id.id,
                "company_id": premier.company_id.id,
            }
            # billing_type (sale_timesheet) est calcule, stocke ET requis. Son
            # calcul ne produit pas de valeur ici et le defaut ne prend pas le
            # relais : la creation echoue sur la contrainte NOT NULL. On le
            # fournit donc explicitement. Ces projets reprennent d'anciennes
            # affaires, ils ne sont pas factures a la tache.
            if "billing_type" in Project._fields:
                vals["billing_type"] = "not_billable"
            projet = Project.create(vals)
            crees += 1

        devis.write({"x_studio_projet": projet.id})
        rattaches += len(devis)

    cr.execute(
        "INSERT INTO ir_logging"
        " (name, type, level, message, path, line, func, dbname, create_date)"
        " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(), now())",
        ("custom",
         f"Migration 19.0.1.0.20: {crees} projet(s) cree(s) depuis les affaires, "
         f"{rattaches} devis rattache(s)",
         __file__, "0", "migrate"),
    )
