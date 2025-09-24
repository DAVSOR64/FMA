from odoo import api, fields, models, tools

class KpiDeliveryBilling(models.Model):
    _name = "kpi.delivery.billing"
    _description = "KPI Facturé / RAF par affaire et livraison planifiée"
    _auto = False
    _rec_name = "sale_order_name"

    sale_order_id   = fields.Many2one("sale.order", string="Affaire", readonly=True)
    sale_order_name = fields.Char(string="Affaire (nom)", readonly=True)
    company_id      = fields.Many2one("res.company", string="Société", readonly=True)
    currency_id     = fields.Many2one("res.currency", string="Devise", readonly=True)

    # Date de référence = livraison planifiée du picking
    scheduled_datetime = fields.Datetime("Livraison planifiée", readonly=True)
    month_date   = fields.Date("Mois (1er jour)", readonly=True)  # pour pivot interval="month"
    iso_year     = fields.Char("Année ISO", readonly=True)
    iso_week     = fields.Char("Semaine ISO", readonly=True)

    # Tag du devis/commande (étiquette)
    tag_id       = fields.Many2one("sale.order.tag", string="Étiquette", readonly=True)
    tag_name     = fields.Char("Nom de l'étiquette", readonly=True)

    amount_invoiced   = fields.Monetary("Facturé HT", currency_field="currency_id", readonly=True)
    amount_to_invoice = fields.Monetary("RAF HT",     currency_field="currency_id", readonly=True)  # reste à facturer

    def _select(self):
        # NOTE:
        # - Montants HT pro-ratés sur quantités (robuste).
        # - RAF = qty_to_invoice * (prix unitaire HT) => c'est déjà "reste à facturer" net des factures existantes.
        # - Date = stock.picking.scheduled_date (livraison planifiée).
        # - On déplie les tags via la table de relation M2M (LEFT JOIN pour inclure les commandes sans tag).
        return """
            SELECT
                MIN(row_id) AS id,
                so.id           AS sale_order_id,
                so.name         AS sale_order_name,
                so.company_id   AS company_id,
                so.currency_id  AS currency_id,

                sp.scheduled_date              AS scheduled_datetime,
                date_trunc('month', sp.scheduled_date)::date AS month_date,
                to_char(sp.scheduled_date, 'IYYY')  AS iso_year,
                to_char(sp.scheduled_date, 'IW')    AS iso_week,

                sot.id          AS tag_id,
                sot.name        AS tag_name,

                SUM(amount_invoiced)   AS amount_invoiced,
                SUM(amount_to_invoice) AS amount_to_invoice
            FROM (
                SELECT
                    (100000000 + COALESCE(sm.id, sol.id)) AS row_id,
                    so.id,
                    sp.scheduled_date,

                    -- prorata quantités (évite les écarts si partiellement facturé)
                    CASE WHEN COALESCE(sol.product_uom_qty,0) = 0 THEN 0
                         ELSE sol.price_subtotal * (sol.qty_invoiced / NULLIF(sol.product_uom_qty,0))
                    END AS amount_invoiced,

                    CASE WHEN COALESCE(sol.product_uom_qty,0) = 0 THEN 0
                         ELSE sol.price_subtotal * (sol.qty_to_invoice / NULLIF(sol.product_uom_qty,0))
                    END AS amount_to_invoice
                FROM sale_order_line sol
                JOIN sale_order so ON so.id = sol.order_id
                LEFT JOIN stock_move sm ON sm.sale_line_id = sol.id AND sm.state != 'cancel'
                LEFT JOIN stock_picking sp ON sp.id = sm.picking_id AND sp.state != 'cancel'
                WHERE so.state IN ('sale','done')
                  AND sp.scheduled_date IS NOT NULL
            ) base
            JOIN sale_order so ON so.id = base.id
            -- Étiquettes (tags) sur la commande :
            LEFT JOIN sale_order_tag_rel rel ON rel.order_id = so.id     -- nom de table M2M (Odoo 17)
            LEFT JOIN sale_order_tag     sot ON sot.id = rel.tag_id
            GROUP BY so.id, so.name, so.company_id, so.currency_id,
                     sp.scheduled_date, sot.id, sot.name
        """

    @api.model
    def init(self):
        tools.drop_view_if_exists(self._cr, self._table)
        self._cr.execute(f"CREATE OR REPLACE VIEW {self._table} AS ({self._select()})")
