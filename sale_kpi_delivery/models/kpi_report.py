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

    scheduled_datetime = fields.Datetime("Livraison planifiée", readonly=True)
    month_date   = fields.Date("Mois (1er jour)", readonly=True)
    iso_year     = fields.Char("Année ISO", readonly=True)
    iso_week     = fields.Char("Semaine ISO", readonly=True)

    # NEW: statut de facturation de la commande (permet de filtrer 'à facturer' + 'rien à facturer')
    invoice_status = fields.Char("Statut facturation", readonly=True)

    # Mesures
    amount_invoiced   = fields.Monetary("Facturé HT", currency_field="currency_id", readonly=True)
    amount_to_invoice = fields.Monetary("RAF HT",     currency_field="currency_id", readonly=True)

    def _select(self):
        # amount_invoiced = Total HT proratisé sur qty_invoiced
        # amount_to_invoice = Total HT - amount_invoiced  (=> RAF net des factures postées)
        return """
            SELECT
                row_number() OVER()                              AS id,
                so.id                                           AS sale_order_id,
                so.name                                         AS sale_order_name,
                so.company_id                                   AS company_id,
                so.currency_id                                  AS currency_id,
                so.invoice_status                               AS invoice_status,
                sp.scheduled_date                               AS scheduled_datetime,
                date_trunc('month', sp.scheduled_date)::date    AS month_date,
                to_char(sp.scheduled_date, 'IYYY')              AS iso_year,
                to_char(sp.scheduled_date, 'IW')                AS iso_week,

                -- Déjà facturé (HT)
                SUM(
                    CASE
                        WHEN COALESCE(sol.product_uom_qty,0) = 0 THEN 0
                        ELSE sol.price_subtotal * (sol.qty_invoiced / NULLIF(sol.product_uom_qty,0))
                    END
                )                                                AS amount_invoiced,

                -- RAF = Total HT - Déjà facturé HT
                SUM(
                    CASE
                        WHEN COALESCE(sol.product_uom_qty,0) = 0 THEN 0
                        ELSE sol.price_subtotal
                             - (sol.price_subtotal * (sol.qty_invoiced / NULLIF(sol.product_uom_qty,0)))
                    END
                )                                                AS amount_to_invoice

            FROM sale_order_line sol
            JOIN sale_order so           ON so.id = sol.order_id
            LEFT JOIN stock_move sm      ON sm.sale_line_id = sol.id AND sm.state != 'cancel'
            LEFT JOIN stock_picking sp   ON sp.id = sm.picking_id    AND sp.state != 'cancel'
            WHERE so.state IN ('sale','done')
              AND sp.scheduled_date IS NOT NULL
            GROUP BY so.id, so.name, so.company_id, so.currency_id, so.invoice_status, sp.scheduled_date
        """

    @api.model
    def init(self):
        tools.drop_view_if_exists(self._cr, self._table)
        self._cr.execute(f"CREATE OR REPLACE VIEW {self._table} AS ({self._select()})")
