from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Filet de sécurité pour x_nb_valide / x_montant_valide.

    Odoo calcule normalement ces champs stockés sur toutes les lignes lors
    de la création des colonnes. On ne rattrape donc que les lignes restées
    à NULL (calcul interrompu, base restaurée en cours de route...) : un
    zéro est une valeur légitime ici, il ne faut surtout pas recalculer
    dessus sous peine de repasser sur toute la table.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})

    cr.execute(
        "SELECT id FROM sale_order"
        " WHERE x_nb_valide IS NULL OR x_montant_valide IS NULL"
    )
    ids = [row[0] for row in cr.fetchall()]
    if not ids:
        return

    orders = env["sale.order"].browse(ids)
    orders._compute_x_nb_valide()
    orders._compute_x_montant_valide()
    cr.execute(
        "INSERT INTO ir_logging"
        " (name, type, level, message, path, line, func, dbname, create_date)"
        " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(), now())",
        ("custom",
         f"Migration 19.0.1.0.30: calculé x_nb_valide/x_montant_valide sur {len(ids)} commande(s) de vente",
         __file__, "0", "migrate"),
    )
