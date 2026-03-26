from odoo import api, fields, models, tools


class KpiDeliveryBilling(models.Model):
    _name = "kpi.delivery.billing"
    _description = "KPI Facturé / RAF / Appro / Stock par affaire et livraison planifiée"
    _auto = False
    _rec_name = "sale_order_name"

    # ── Dimensions ────────────────────────────────────────────────────────────
    sale_order_id = fields.Many2one("sale.order", string="Affaire", readonly=True)
    sale_order_name = fields.Char(string="Affaire (nom)", readonly=True)
    company_id = fields.Many2one("res.company", string="Société", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Devise", readonly=True)
    invoice_status = fields.Char("Statut facturation", readonly=True)

    # ── Temps ─────────────────────────────────────────────────────────────────
    scheduled_datetime = fields.Datetime(
        "Livraison planifiée / Engagement / Date commande", readonly=True
    )
    month_date = fields.Date("Mois (1er jour)", readonly=True)
    iso_year = fields.Char("Année ISO", readonly=True)
    iso_week = fields.Char("Semaine ISO", readonly=True)

    # ── Mesures VENTE ─────────────────────────────────────────────────────────
    amount_invoiced = fields.Monetary(
        "Facturé HT",
        currency_field="currency_id",
        readonly=True,
        help="Montant HT réellement facturé sur factures clients postées (net avoirs).",
    )
    amount_to_invoice = fields.Monetary(
        "RAF HT (reste à facturer)",
        currency_field="currency_id",
        readonly=True,
        help="Total vente HT − Facturé HT. Jamais négatif.",
    )
    order_count = fields.Integer("Nb devis", readonly=True)

    # ── Mesures APPRO (purchase) ──────────────────────────────────────────────
    amount_purchase_total = fields.Monetary(
        "Total appro HT",
        currency_field="currency_id",
        readonly=True,
        help="Montant total HT des commandes d'achat liées à l'affaire "
             "(via sale_order_line_id ou sale_order_id sur purchase.order.line).",
    )
    amount_po_not_delivered_not_invoiced = fields.Monetary(
        "Appro : non livrées / non facturées",
        currency_field="currency_id",
        readonly=True,
        help="Lignes d'achat dont qty_received = 0 et qty_invoiced = 0.",
    )
    amount_po_delivered_not_invoiced = fields.Monetary(
        "Appro : livrées / non facturées",
        currency_field="currency_id",
        readonly=True,
        help="Lignes d'achat dont qty_received > 0 et qty_invoiced = 0 (ou partiel).",
    )
    amount_po_delivered_invoiced = fields.Monetary(
        "Appro : livrées et facturées",
        currency_field="currency_id",
        readonly=True,
        help="Lignes d'achat dont qty_received > 0 et qty_invoiced > 0.",
    )

    # ── Mesures STOCK / MRP ───────────────────────────────────────────────────
    amount_stock_consumed = fields.Monetary(
        "Stock consommé (nomenclature)",
        currency_field="currency_id",
        readonly=True,
        help="Valeur HT des composants consommés dans les ordres de fabrication "
             "liés à l'affaire (via mrp.production.sale_id ou origin).",
    )

    # =========================================================================
    # SQL helpers
    # =========================================================================

    def _invoiced_subquery(self):
        """
        Agrège le montant HT facturé par sale_order_line depuis account.move.line.
        Gère la M2M Odoo 17+ (account_move_line__sale_line_ids) et legacy.
        Montant POSITIF pour factures, NÉGATIF pour avoirs.
        """
        self._cr.execute(
            "SELECT to_regclass('public.account_move_line__sale_line_ids')"
        )
        has_new_rel = bool(self._cr.fetchone()[0])

        if has_new_rel:
            rel_table = "account_move_line__sale_line_ids"
            aml_id_col = "account_move_line_id"
            sol_id_col = "sale_order_line_id"
        else:
            rel_table = "sale_order_line_invoice_rel"
            aml_id_col = "invoice_line_id"
            sol_id_col = "order_line_id"

        return f"""
            SELECT
                rel.{sol_id_col}                          AS sol_id,
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
                )                                          AS amt_invoiced_line
            FROM {rel_table} rel
            JOIN account_move_line aml ON aml.id  = rel.{aml_id_col}
            JOIN account_move       am  ON am.id   = aml.move_id
            WHERE am.state = 'posted'
              AND am.move_type IN ('out_invoice','out_refund')
              AND COALESCE(aml.display_type,'') = ''
            GROUP BY rel.{sol_id_col}
        """

    def _purchase_subquery(self):
        """
        Agrège par sale_order_id les montants d'appro selon l'état de livraison
        et de facturation des lignes d'achat.

        Priorité de lien :
          1. sale_order_id direct sur purchase.order.line  (champ custom ou natif)
          2. sale_order_line_id sur purchase.order.line    (règle MTO Odoo)
        """
        self._cr.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name='purchase_order_line' AND column_name='sale_order_id'
        """)
        has_so_direct = bool(self._cr.fetchone())

        self._cr.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name='purchase_order_line' AND column_name='sale_order_line_id'
        """)
        has_sol_link = bool(self._cr.fetchone())

        if not has_so_direct and not has_sol_link:
            return """
                SELECT NULL::integer AS sale_order_id,
                       0::numeric   AS amt_po_total,
                       0::numeric   AS amt_po_not_del_not_inv,
                       0::numeric   AS amt_po_del_not_inv,
                       0::numeric   AS amt_po_del_inv
                WHERE false
            """

        if has_so_direct:
            so_col = "pol.sale_order_id"
            extra_join = ""
        else:
            so_col = "sol_link.order_id"
            extra_join = "LEFT JOIN sale_order_line sol_link ON sol_link.id = pol.sale_order_line_id"

        return f"""
            SELECT
                {so_col}                                   AS sale_order_id,
                SUM(pol.price_subtotal)                    AS amt_po_total,
                SUM(
                    CASE WHEN COALESCE(pol.qty_received,0) = 0
                          AND COALESCE(pol.qty_invoiced,0) = 0
                         THEN pol.price_subtotal ELSE 0 END
                )                                          AS amt_po_not_del_not_inv,
                SUM(
                    CASE WHEN COALESCE(pol.qty_received,0) > 0
                          AND COALESCE(pol.qty_invoiced,0) = 0
                         THEN pol.price_subtotal ELSE 0 END
                )                                          AS amt_po_del_not_inv,
                SUM(
                    CASE WHEN COALESCE(pol.qty_received,0) > 0
                          AND COALESCE(pol.qty_invoiced,0) > 0
                         THEN pol.price_subtotal ELSE 0 END
                )                                          AS amt_po_del_inv
            FROM purchase_order_line pol
            JOIN purchase_order po ON po.id = pol.order_id
            {extra_join}
            WHERE po.state IN ('purchase','done')
              AND COALESCE(pol.display_type,'') = ''
              AND {so_col} IS NOT NULL
            GROUP BY {so_col}
        """

    def _stock_subquery(self):
        """
        Valeur des composants consommés dans les ordres de fabrication liés
        à une affaire de vente.

        Lien MRP → affaire : mrp.production.sale_id (natif Odoo 16+)
        ou fallback sur origin (nom de la SO).

        Valorisation : stock_valuation_layer.value si disponible,
        sinon qty_done × coût standard (standard_price sur la variante).
        """
        # Vérifier l'existence de la table mrp_production
        self._cr.execute("SELECT to_regclass('public.mrp_production')")
        if not self._cr.fetchone()[0]:
            return """
                SELECT NULL::integer AS sale_order_id,
                       0::numeric   AS amt_stock_consumed
                WHERE false
            """

        self._cr.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name='mrp_production' AND column_name='sale_id'
        """)
        has_sale_id = bool(self._cr.fetchone())

        if has_sale_id:
            so_col = "mp.sale_id"
            so_where = "mp.sale_id IS NOT NULL"
        else:
            so_col = """(SELECT so_fb.id FROM sale_order so_fb
                         WHERE so_fb.name = mp.origin LIMIT 1)"""
            so_where = "mp.origin IS NOT NULL"

        self._cr.execute("SELECT to_regclass('public.stock_valuation_layer')")
        has_svl = bool(self._cr.fetchone()[0])

        # En Odoo 17+, standard_price n'est plus une colonne SQL directe
        # (stockée via ir.property / product.price.history).
        # On utilise stock_valuation_layer.value quand disponible,
        # sinon on valorise à 0 (la SVL est toujours présente en Odoo 17+).
        if has_svl:
            value_expr = "ABS(COALESCE(svl.value, 0))"
            svl_join = "LEFT JOIN stock_valuation_layer svl ON svl.stock_move_id = sm.id"
            pt_join = ""
        else:
            # Fallback Odoo < 16 : pas de SVL, on met 0 (pas d'accès SQL au coût standard)
            value_expr = "0"
            svl_join = ""
            pt_join = ""

        return f"""
            SELECT
                {so_col}                                   AS sale_order_id,
                SUM({value_expr})                          AS amt_stock_consumed
            FROM mrp_production mp
            JOIN stock_move sm
                ON  sm.production_id = mp.id
                AND sm.state         = 'done'
                AND sm.scrapped      = false
            JOIN product_product pp ON pp.id = sm.product_id
            {svl_join}
            {pt_join}
            WHERE mp.state IN ('done','progress')
              AND {so_where}
            GROUP BY {so_col}
        """

    def _select(self):
        invoiced_sql = self._invoiced_subquery()
        purchase_sql = self._purchase_subquery()
        stock_sql    = self._stock_subquery()

        return f"""
            WITH sol_base AS (
                -- Lignes de vente actives (hors sections/notes)
                SELECT
                    sol.id                                                          AS sol_id,
                    so.id                                                           AS sale_order_id,
                    so.name                                                         AS sale_order_name,
                    so.company_id,
                    so.currency_id,
                    so.invoice_status,
                    COALESCE(sp.scheduled_date, so.commitment_date, so.date_order)  AS scheduled_ref,
                    sol.price_subtotal                                              AS line_total_ht
                FROM sale_order_line sol
                JOIN sale_order so
                    ON so.id  = sol.order_id
                LEFT JOIN stock_move sm
                    ON  sm.sale_line_id = sol.id
                    AND sm.state       != 'cancel'
                LEFT JOIN stock_picking sp
                    ON  sp.id    = sm.picking_id
                    AND sp.state != 'cancel'
                WHERE so.state IN ('sale','done')
                  AND COALESCE(sol.display_type,'') = ''
            ),

            -- Agrégats vente par affaire + date de référence
            sale_agg AS (
                SELECT
                    sale_order_id,
                    company_id,
                    currency_id,
                    invoice_status,
                    scheduled_ref,
                    sale_order_name,
                    SUM(line_total_ht)     AS amt_sale_total,
                    COUNT(DISTINCT sol_id) AS cnt_lines
                FROM sol_base
                GROUP BY
                    sale_order_id, company_id, currency_id,
                    invoice_status, scheduled_ref, sale_order_name
            ),

            -- Montant facturé par ligne de vente
            inv AS (
                {invoiced_sql}
            ),

            -- Montant facturé agrégé par affaire + date de référence
            inv_agg AS (
                SELECT
                    b.sale_order_id,
                    b.scheduled_ref,
                    SUM(COALESCE(i.amt_invoiced_line, 0)) AS amt_invoiced
                FROM sol_base b
                LEFT JOIN inv i ON i.sol_id = b.sol_id
                GROUP BY b.sale_order_id, b.scheduled_ref
            ),

            -- Données appro par affaire
            po_agg AS (
                {purchase_sql}
            ),

            -- Stock / MRP consommé par affaire
            stock_agg AS (
                {stock_sql}
            )

            SELECT
                row_number() OVER ()                            AS id,
                sa.sale_order_id,
                sa.sale_order_name,
                sa.company_id,
                sa.currency_id,
                sa.invoice_status,
                sa.scheduled_ref                                AS scheduled_datetime,
                date_trunc('month', sa.scheduled_ref)::date     AS month_date,
                to_char(sa.scheduled_ref, 'IYYY')               AS iso_year,
                to_char(sa.scheduled_ref, 'IW')                 AS iso_week,

                -- ── Vente ─────────────────────────────────────────────────
                COALESCE(ia.amt_invoiced, 0)                    AS amount_invoiced,
                GREATEST(
                    sa.amt_sale_total - COALESCE(ia.amt_invoiced, 0),
                    0
                )                                               AS amount_to_invoice,
                sa.cnt_lines                                    AS order_count,

                -- ── Appro ─────────────────────────────────────────────────
                COALESCE(po.amt_po_total,           0)          AS amount_purchase_total,
                COALESCE(po.amt_po_not_del_not_inv, 0)          AS amount_po_not_delivered_not_invoiced,
                COALESCE(po.amt_po_del_not_inv,     0)          AS amount_po_delivered_not_invoiced,
                COALESCE(po.amt_po_del_inv,         0)          AS amount_po_delivered_invoiced,

                -- ── Stock / MRP ───────────────────────────────────────────
                COALESCE(st.amt_stock_consumed,     0)          AS amount_stock_consumed

            FROM sale_agg sa
            LEFT JOIN inv_agg  ia ON ia.sale_order_id = sa.sale_order_id
                                  AND ia.scheduled_ref  = sa.scheduled_ref
            LEFT JOIN po_agg   po ON po.sale_order_id  = sa.sale_order_id
            LEFT JOIN stock_agg st ON st.sale_order_id  = sa.sale_order_id
        """

    # ── Création de la vue SQL ────────────────────────────────────────────────

    @api.model
    def init(self):
        tools.drop_view_if_exists(self._cr, self._table)
        self._cr.execute(
            f"CREATE OR REPLACE VIEW {self._table} AS ({self._select()})"
        )
