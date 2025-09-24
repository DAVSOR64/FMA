from odoo import api, fields, models, tools

class KpiDeliveryBilling(models.Model):
    _name = "kpi.delivery.billing"
    _description = "KPI Facturé / RAF par affaire et livraison planifiée"
    _auto = False
    _rec_name = "sale_order_name"

    # Dimensions
    sale_order_id   = fields.Many2one("sale.order", string="Affaire", readonly=True)
    sale_order_name = fields.Char(string="Affaire (nom)", readonly=True)
    company_id      = fields.Many2one("res.company", string="Société", readonly=True)
    currency_id     = fields.Many2one("res.currency", string="Devise", readonly=True)
    invoice_status  = fields.Char("Statut facturation", readonly=True)

    # Temps (date liv/engagement/commande)
    scheduled_datetime = fields.Datetime("Livraison planifiée / Engagement / Date commande", readonly=True)
    month_date   = fields.Date("Mois (1er jour)", readonly=True)
    iso_year     = fields.Char("Année ISO", readonly=True)
    iso_week     = fields.Char("Semaine ISO", readonly=True)

    # Mesures
    amount_invoiced   = fields.Monetary("Facturé HT", currency_field="currency_id", readonly=True)
    amount_to_invoice = fields.Monetary("RAF HT",     currency_field="currency_id", readonly=True)
    order_count       = fields.Integer("Nb devis", readonly=True)

    # --- SQL helpers --------------------------------------------------------

    def _invoiced_subquery(self):
        """
        Retourne un SQL qui agrège le montant HT facturé par sale_order_line (depuis account.move.line),
        en gérant la M2M Odoo 17 ('account_move_line__sale_line_ids') ou legacy
        ('sale_order_line_invoice_rel').
        Le montant est POSITIF pour les factures, NÉGATIF pour les avoirs.
        """
        # Détecter la table M2M moderne (Odoo 14+ / 17)
        self._cr.execute("SELECT to_regclass('public.account_move_line__sale_line_ids')")
        has_new_rel = bool(self._cr.fetchone()[0])

        if has_new_rel:
            # Colonnes: account_move_line_id, sale_order_line_id
            rel_table = "account_move_line__sale_line_ids"
            aml_id_col = "account_move_line_id"
            sol_id_col = "sale_order_line_id"
        else:
            # Legacy: sale_order_line_invoice_rel (invoice_line_id, order_line_id)
            rel_table = "sale_order_line_invoice_rel"
            aml_id_col = "invoice_line_id"
            sol_id_col = "order_line_id"

        return f"""
            SELECT
                rel.{sol_id_col} AS sol_id,
                SUM(
                    CASE
                        WHEN am.state = 'posted'
                         AND am.move_type IN ('out_invoice','out_refund')
                        THEN
                            CASE WHEN am.move_type = 'out_refund'
                                 THEN -aml.price_subtotal
                                 ELSE  aml.price_subtotal
                            END
                        ELSE 0
                    END
                ) AS amt_invoiced_line
            FROM {rel_table} rel
            JOIN account_move_line aml ON aml.id = rel.{aml_id_col}
            JOIN account_move am       ON am.id  = aml.move_id
            WHERE (am.state = 'posted' AND am.move_type IN ('out_invoice','out_refund'))
              AND COALESCE(aml.display_type,'') = ''         -- pas de lignes de section/note
            GROUP BY rel.{sol_id_col}
        """

    def _select(self):
        """
        Base = lignes de vente (hors sections/notes), avec date de référence.
        On joint ensuite le montant facturé issu des factures client postées.
        """
        invoiced_sql = self._invoiced_subquery()

        return f"""
            WITH sol_base AS (
                SELECT
                    sol.id                        AS sol_id,
                    so.id                         AS sale_order_id,
                    so.name                       AS sale_order_name,
                    so.company_id                 AS company_id,
                    so.currency_id                AS currency_id,
                    so.invoice_status             AS invoice_status,
                    COALESCE(sp.scheduled_date, so.commitment_date, so.date_order) AS scheduled_ref,
                    sol.price_subtotal            AS line_total_ht
                FROM sale_order_line sol
                JOIN sale_order so         ON so.id = sol.order_id
                LEFT JOIN stock_move sm    ON sm.sale_line_id = sol.id AND sm.state != 'cancel'
                LEFT JOIN stock_picking sp ON sp.id = sm.picking_id    AND sp.state != 'cancel'
                WHERE so.state IN ('sale','done')
                  AND COALESCE(sol.display_type,'') = ''   -- exclure sections/notes
            ),
            inv AS (
                {invoiced_sql}
            )
            SELECT
                row_number() OVER()                      AS id,
                b.sale_order_id,
                b.sale_order_name,
                b.company_id,
                b.currency_id,
                b.invoice_status,
                b.scheduled_ref                          AS scheduled_datetime,
                date_trunc('month', b.scheduled_ref)::date AS month_date,
                to_char(b.scheduled_ref, 'IYYY')         AS iso_year,
                to_char(b.scheduled_ref, 'IW')           AS iso_week,

                -- Montant facturé HT depuis les factures postées (factures - avoirs)
                SUM(COALESCE(i.amt_invoiced_line, 0))    AS amount_invoiced,

                -- RAF = Total lignes - Déjà facturé (jamais < 0)
                GREATEST(
                    SUM(b.line_total_ht) - SUM(COALESCE(i.amt_invoiced_line, 0)),
                    0
                )                                         AS amount_to_invoice,

                COUNT(DISTINCT b.sol_id)                  AS order_count
            FROM sol_base b
            LEFT JOIN inv i ON i.sol_id = b.sol_id
            GROUP BY
                b.sale_order_id, b.sale_order_name, b.company_id, b.currency_id,
                b.invoice_status, b.scheduled_ref
        """

    # --- view creation ------------------------------------------------------

    @api.model
    def init(self):
        tools.drop_view_if_exists(self._cr, self._table)
        self._cr.execute(f"CREATE OR REPLACE VIEW {self._table} AS ({self._select()})")
