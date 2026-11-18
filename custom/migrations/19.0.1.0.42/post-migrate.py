# Normalisation des noms : minuscules et sans accents. On n'utilise pas
# l'extension unaccent, qui n'est pas installee sur toutes les bases.
SANS_ACCENT = (
    "àâäéèêëîïôöùûüçÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ",
    "aaaeeeeiioouuucaaaeeeeiioouuuc",
)

# Deux valeurs historiques comportent une faute de frappe que rien ne permet
# de deviner automatiquement : lettres inversees, consonne changee. La
# correspondance a ete validee par le metier.
CORRECTIONS = {
    "Hubert BOURDARAIS": "Hubert BOURDARIAS",
    "Christian GUILLARD": "Christian GUIHARD",
}


def migrate(cr, version):
    """Rattache un employe aux clients qui n'ont qu'un nom de commercial.

    Le commercial etait porte par une selection de texte libre
    (res.partner.part_commercial). Il devient un Many2one vers hr.employee
    (x_studio_commercial_1), seul capable de servir la remuneration et le
    filtrage des tableaux de bord.

    Le rapprochement se fait **par nom**, jamais par identifiant : les ids
    d'employes different d'un environnement a l'autre, un mapping fige en dur
    rattacherait les mauvaises personnes en production.

    Mesure sur la staging : 439 clients concernes, 6 valeurs distinctes, 100 %
    rattachees. Les valeurs qui ne designent pas une personne (« A DEFINIR »,
    « Sans Affectation »...) correspondent a des fiches employe existantes et
    sont donc reprises telles quelles : « non encore affecte » est une
    information, un champ vide n'en est pas une.

    Les clients qui ont deja un employe ne sont pas touches, meme quand il
    diverge du texte : 691 cas mesures, et c'est le Many2one qui fait foi.
    """
    corrections = " ".join(
        cr.mogrify("WHEN %s THEN %s", (source, cible)).decode()
        for source, cible in CORRECTIONS.items()
    )

    cr.execute(
        f"""
        UPDATE res_partner p
        SET    x_studio_commercial_1 = e.id
        FROM   hr_employee e
        JOIN   resource_resource r ON r.id = e.resource_id
        WHERE  p.customer_rank > 0
          AND  p.x_studio_commercial_1 IS NULL
          AND  p.part_commercial IS NOT NULL
          AND  p.part_commercial <> ''
          AND  lower(translate(r.name, %s, %s)) =
               lower(translate(CASE p.part_commercial {corrections}
                               ELSE p.part_commercial END, %s, %s))
        """,
        SANS_ACCENT + SANS_ACCENT,
    )
    rattaches = cr.rowcount
    if not rattaches:
        return

    cr.execute(
        "INSERT INTO ir_logging"
        " (name, type, level, message, path, line, func, dbname, create_date)"
        " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(), now())",
        ("custom",
         f"Migration 19.0.1.0.42: commercial rattache a un employe sur "
         f"{rattaches} client(s)",
         __file__, "0", "migrate"),
    )
