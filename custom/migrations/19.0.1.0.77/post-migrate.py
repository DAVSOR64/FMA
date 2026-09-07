# -*- coding: utf-8 -*-
"""Renseigne « Projet de la vente » sur les OF et les transferts.

La version precedente confiait ce travail a un recalcul de masse
(env.add_to_compute + flush_all). En production, ce recalcul a porte sur 3834
ordres de fabrication et n'a ecrit strictement aucune valeur, sans lever la
moindre erreur. Une reparation dont on ne peut pas dire si elle a eu lieu n'en
est pas une.

Ici, plus de mecanique : six UPDATE, dont on lit le nombre de lignes touchees.

Toutes les clauses portent un « IS NULL » sur la cible. Consequence : le
script n'ecrase jamais une valeur existante, et il peut etre rejoue autant de
fois que necessaire. C'est la lecon du jour ou le recalcul a vide le champ sur
toute la base.

L'ordre compte : les OF d'abord, puisque les passes 5 et 6 recopient depuis
eux.
"""
from odoo import api, SUPERUSER_ID

#: Les passes, dans l'ordre. (libelle, SQL)
PASSES = [
    ("OF <- commande (lien direct)", """
        UPDATE mrp_production mo
           SET x_studio_projet_de_la_vente = so.x_studio_projet
          FROM sale_order so
         WHERE so.id = mo.x_studio_mtn_mrp_sale_order
           AND so.x_studio_projet IS NOT NULL
           AND mo.x_studio_projet_de_la_vente IS NULL
    """),
    ("OF <- commande (ligne de commande)", """
        UPDATE mrp_production mo
           SET x_studio_projet_de_la_vente = so.x_studio_projet
          FROM sale_order_line sol
          JOIN sale_order so ON so.id = sol.order_id
         WHERE sol.id = mo.sale_line_id
           AND so.x_studio_projet IS NOT NULL
           AND mo.x_studio_projet_de_la_vente IS NULL
    """),
    ("Transferts <- commande", """
        UPDATE stock_picking p
           SET x_studio_projet_de_la_vente = so.x_studio_projet
          FROM sale_order so
         WHERE so.id = p.sale_id
           AND so.x_studio_projet IS NOT NULL
           AND p.x_studio_projet_de_la_vente IS NULL
    """),
    ("Transferts <- OF (mouvements)", """
        UPDATE stock_picking p
           SET x_studio_projet_de_la_vente = sub.pj
          FROM (SELECT m.picking_id AS pid,
                       max(mo.x_studio_projet_de_la_vente) AS pj
                  FROM stock_move m
                  JOIN mrp_production mo
                    ON mo.id = COALESCE(m.production_id,
                                        m.raw_material_production_id)
                 WHERE m.picking_id IS NOT NULL
                   AND mo.x_studio_projet_de_la_vente IS NOT NULL
                 GROUP BY m.picking_id) sub
         WHERE p.id = sub.pid
           AND p.x_studio_projet_de_la_vente IS NULL
    """),
    ("Transferts <- OF (origine)", """
        UPDATE stock_picking p
           SET x_studio_projet_de_la_vente = mo.x_studio_projet_de_la_vente
          FROM mrp_production mo
         WHERE mo.name = p.origin
           AND mo.x_studio_projet_de_la_vente IS NOT NULL
           AND p.x_studio_projet_de_la_vente IS NULL
    """),
]


def _colonne_existe(cr, table, colonne):
    cr.execute(
        "SELECT 1 FROM information_schema.columns"
        " WHERE table_name = %s AND column_name = %s", (table, colonne))
    return bool(cr.fetchone())


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    # Sans « Projet mtn » sur la commande il n'y a rien a recopier : sur une
    # base ou ce champ Studio n'existe pas, on sort sans bruit.
    if not _colonne_existe(cr, "sale_order", "x_studio_projet"):
        return

    journal = []
    for libelle, requete in PASSES:
        cr.execute(requete)
        journal.append("%s : %s" % (libelle, cr.rowcount))

    # Les OF que les deux premieres passes n'ont pas atteints : reference_ids
    # est une relation v19 dont le nom de table n'est pas devinable, on laisse
    # l'ORM la resoudre. C'est ce chemin qui alimente le bouton « Ventes ».
    Production = env["mrp.production"]
    poses = 0
    if hasattr(Production, "_fma_commande_de_la_vente"):
        restants = Production.search(
            [("x_studio_projet_de_la_vente", "=", False)])
        for debut in range(0, len(restants), 500):
            for production in restants[debut:debut + 500]:
                commande = production._fma_commande_de_la_vente()
                projet = (
                    commande.x_studio_projet
                    if commande and "x_studio_projet" in commande._fields
                    else False
                )
                if projet:
                    cr.execute(
                        "UPDATE mrp_production"
                        "   SET x_studio_projet_de_la_vente = %s"
                        " WHERE id = %s"
                        "   AND x_studio_projet_de_la_vente IS NULL",
                        (projet.id, production.id))
                    poses += cr.rowcount
            env.invalidate_all()
    journal.append("OF <- commande (reference_ids) : %s" % poses)

    cr.execute(
        "INSERT INTO ir_logging"
        " (name, type, level, message, path, line, func, dbname, create_date)"
        " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(),"
        " now())",
        ("custom",
         "Migration : Projet de la vente — %s" % ", ".join(journal),
         __file__, "0", "migrate"),
    )
