# Normalisation des noms : minuscules et sans accents, comme en 19.0.1.0.42.
# On n'utilise pas l'extension unaccent, absente de certaines bases.
SANS_ACCENT = (
    "àâäéèêëîïôöùûüçÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ",
    "aaaeeeeiioouuucaaaeeeeiioouuuc",
)


def _colonne_existe(cr, table, colonne):
    """Les colonnes posees par fma_sale_order_custom ne sont pas garanties.

    Ce script vit dans « custom », qui se charge AVANT fma_sale_order_custom.
    Sur une base neuve, x_studio_commercial_1 n'existe pas encore : mieux vaut
    ne rien faire que casser le deploiement. La reprise se jouera au bump
    suivant, quand la colonne sera la.
    """
    cr.execute(
        "SELECT 1 FROM information_schema.columns"
        " WHERE table_name = %s AND column_name = %s",
        (table, colonne),
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    """Rattache commercial_id au commercial du DOCUMENT, pas a celui du client.

    Constat qui motive ce script : commercial_id a ete calcule depuis
    res_partner.x_studio_commercial_1, c'est-a-dire depuis l'employe qui suit
    le client *aujourd'hui*. Mesure sur la staging : sur 5 309 factures
    postees, 4 418 auraient ainsi porte un autre nom que celui imprime, et pas
    par variante d'orthographe — « Quentin MOREAU » devenait « Romain HELIE »
    sur 292 factures. Six ans d'attribution commerciale reecrits.

    La bonne source existe et elle est propre : sale_order.x_studio_commercial_1,
    le nom fige a l'etablissement du devis. 13 494 devis le portent, et les
    13 494 trouvent un employe par rapprochement de nom — zero orphelin.

    On procede donc en deux temps :

    1. Le devis prend l'employe correspondant a son propre texte historique.
    2. La facture prend le commercial du devis dont elle est issue, par ses
       lignes. Une facture sans devis identifie reste vide : le rapport et le
       formulaire retombent alors sur inv_commercial, exactement comme avant.

    Les corrections d'orthographe validees par le metier en 19.0.1.0.42 ne
    sont pas rejouees ici : les 13 494 textes des devis tombent juste sans
    elles. Elles ne concernaient que le referentiel client.
    """
    if not _colonne_existe(cr, "sale_order", "x_studio_commercial_1"):
        return

    # --- 1. Les devis -------------------------------------------------------
    # ORDER BY e.id dans le sous-select : deux employes peuvent porter le meme
    # nom, et une migration doit donner le meme resultat a chaque execution.
    cr.execute(
        """
        UPDATE sale_order so
        SET    commercial_id = (
                   SELECT e.id
                   FROM   hr_employee e
                   JOIN   resource_resource r ON r.id = e.resource_id
                   WHERE  lower(translate(r.name, %s, %s))
                        = lower(translate(so.x_studio_commercial_1, %s, %s))
                   ORDER  BY e.id
                   LIMIT  1
               )
        WHERE  coalesce(so.x_studio_commercial_1, '') <> ''
          AND  EXISTS (
                   SELECT 1
                   FROM   hr_employee e
                   JOIN   resource_resource r ON r.id = e.resource_id
                   WHERE  lower(translate(r.name, %s, %s))
                        = lower(translate(so.x_studio_commercial_1, %s, %s))
               )
        """,
        SANS_ACCENT + SANS_ACCENT + SANS_ACCENT + SANS_ACCENT,
    )
    devis = cr.rowcount

    # --- 2. Les factures ----------------------------------------------------
    # Uniquement celles qui n'ont pas de commercial : une valeur deja presente
    # vient de _prepare_invoice ou d'une correction manuelle, et fait foi.
    cr.execute(
        """
        UPDATE account_move m
        SET    commercial_id = (
                   SELECT so.commercial_id
                   FROM   account_move_line aml
                   JOIN   sale_order_line_invoice_rel rel
                          ON rel.invoice_line_id = aml.id
                   JOIN   sale_order_line sol ON sol.id = rel.order_line_id
                   JOIN   sale_order so ON so.id = sol.order_id
                   WHERE  aml.move_id = m.id
                     AND  so.commercial_id IS NOT NULL
                   ORDER  BY so.id
                   LIMIT  1
               )
        WHERE  m.move_type IN ('out_invoice', 'out_refund')
          AND  m.commercial_id IS NULL
          AND  EXISTS (
                   SELECT 1
                   FROM   account_move_line aml
                   JOIN   sale_order_line_invoice_rel rel
                          ON rel.invoice_line_id = aml.id
                   JOIN   sale_order_line sol ON sol.id = rel.order_line_id
                   JOIN   sale_order so ON so.id = sol.order_id
                   WHERE  aml.move_id = m.id
                     AND  so.commercial_id IS NOT NULL
               )
        """
    )
    factures = cr.rowcount

    cr.execute(
        "INSERT INTO ir_logging"
        " (name, type, level, message, path, line, func, dbname, create_date)"
        " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(), now())",
        ("custom",
         f"Migration 19.0.1.0.49: commercial du document repris sur "
         f"{devis} devis et {factures} facture(s)",
         __file__, "0", "migrate"),
    )
