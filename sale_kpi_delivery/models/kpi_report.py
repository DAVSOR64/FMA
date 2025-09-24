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

    # Champs tags (étiquettes) — peuvent rester vides si tags absents en base
    tag_id       = fields.Many2one(comodel_name="ir.model", string="Étiquette (id)", readonly=True)  # type neutre
    tag_name     = fields.Char("Étiquette", readonly=True)

    amount_invoiced   = fields.Monetary("Facturé HT", currency_field="currency_id", readonly=True)
    amount_to_invoice = fields.Monetary("RAF HT",     currency_field="currency_id", readonly=True)

    def _base_subquery(self):
        # Montants pro-ratés par quantités, date = scheduled_date du picking
        return """
            SELECT
                (100000000 + COALESCE(sm.id, sol.id)) AS row_id,
                so.id       AS sale_order_id,
                so.name     AS sale_order_name,
                so.company_id,
                so.currency_id,
                sp.scheduled_date AS scheduled_datetime,
                date_trunc('month', sp.scheduled_date)::date AS month_date,
                to_char(sp.scheduled_date, 'IYYY') AS iso_year,
                to_char(sp.scheduled_date, 'IW')   AS iso_week,
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
        """

    @api.model
    def init(self):
        tools.drop_view_if_exists(self._cr, self._table)

        # Détection des tables de tags possibles
        self._cr.execute("SELECT to_regclass('public.sale_order_tag')")
        has_sale_order_tag = bool(self._cr.fetchone()[0])

        self._cr.execute("SELECT to_regclass('public.sale_order_tag_rel')")
        has_rel_1 = bool(self._cr.fetchone()[0])

        self._cr.execute("SELECT to_regclass('public.sale_order_sale_order_tag_rel')")
        has_rel_2 = bool(self._cr.fetchone()[0])

        # on construit le SQL final
        base = self._base_subquery()

        if has_sale_order_tag and (has_rel_1 or has_rel_2):
            rel_table = "sale_order_tag_rel" if has_rel_1 else "sale_order_sale_order_tag_rel"
            select_sql = f"""
                SELECT
                    MIN(row_id) AS id,
                    sale_order_id,
                    sale_order_name,
                    company_id,
                    currency_id,
                    scheduled_datetime,
                    month_date,
                    iso_year,
                    iso_week,
                    sot.id   AS tag_id,
                    sot.name AS tag_name,
                    SUM(amount_invoiced)   AS amount_invoiced,
                    SUM(amount_to_invoice) AS amount_to_invoice
                FROM ({base}) b
                LEFT JOIN {rel_table} rel ON rel.order_id = b.sale_order_id
                LEFT JOIN sale_order_tag sot ON sot.id = rel.tag_id
                GROUP BY sale_order_id, sale_order_name, company_id, currency_id,
                         scheduled_datetime, month_date, iso_year, iso_week, sot.id, sot.name
            """
        else:
            # Pas de tables de tags : on met des NULL pour tag_id/tag_name
            select_sql = f"""
                SELECT
                    MIN(row_id) AS id,
                    sale_order_id,
                    sale_order_name,
                    company_id,
                    currency_id,
                    scheduled_datetime,
                    month_date,
                    iso_year,
                    iso_week,
                    NULL::integer AS tag_id,
                    NULL::varchar AS tag_name,
                    SUM(amount_invoiced)   AS amount_invoiced,
                    SUM(amount_to_invoice) AS amount_to_invoice
                FROM ({base}) b
                GROUP BY sale_order_id, sale_order_name, company_id, currency_id,
                         scheduled_datetime, month_date, iso_year, iso_week
            """

        self._cr.execute(f"CREATE VIEW {self._table} AS {select_sql}")
