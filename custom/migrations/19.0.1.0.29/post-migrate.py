from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Filet de sécurité pour le nouveau champ stocké x_tranche_montant.

    Odoo calcule normalement un champ stocké calculé sur toutes les lignes
    lors de la création de la colonne. On repasse malgré tout sur les
    devis/commandes restés à NULL (calcul interrompu, base restaurée en
    cours de route...) afin qu'aucune ligne ne sorte des regroupements et
    filtres par tranche.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})

    orders = env["sale.order"].search([("x_tranche_montant", "=", False)])
    if not orders:
        return

    orders._compute_x_tranche_montant()
    cr.execute(
        "INSERT INTO ir_logging"
        " (name, type, level, message, path, line, func, dbname, create_date)"
        " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(), now())",
        ("custom",
         f"Migration 19.0.1.0.29: calculé x_tranche_montant sur {len(orders)} commande(s) de vente",
         __file__, "0", "migrate"),
    )
