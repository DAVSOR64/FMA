from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Recalcule x_is_glazing_order sur les commandes d'achat existantes.

    Le nom de catégorie utilisé par _compute_x_is_glazing_order a été
    corrigé ("Remplissage" -> "02_REMPLISSAGE", retour métier T-13,
    29/07). Champ stocké : les commandes déjà créées avant ce correctif
    gardent leur ancienne valeur (False) tant que rien ne déclenche un
    recalcul -- d'où les colonnes Hauteur/Largeur/Repère et les champs
    remise/commentaires vitrage encore invisibles sur des commandes qui
    ont pourtant bien une ligne vitrage (ex. P27151, confirmé en base).
    """
    env = api.Environment(cr, SUPERUSER_ID, {})

    categ = env["product.category"].search([("name", "=", "02_REMPLISSAGE")], limit=1)
    if not categ:
        return

    orders = env["purchase.order"].search([
        ("x_is_glazing_order", "=", False),
        ("order_line.product_id.categ_id", "=", categ.id),
    ])
    if orders:
        orders._compute_x_is_glazing_order()
        cr.execute(
            "INSERT INTO ir_logging"
            " (name, type, level, message, path, line, func, dbname, create_date)"
            " VALUES (%s, 'server', 'INFO', %s, %s, %s, %s, current_database(), now())",
            ("custom",
             f"Migration 19.0.1.0.23: recalculé x_is_glazing_order sur {len(orders)} commande(s) d'achat (T-13)",
             __file__, "0", "migrate"),
        )
