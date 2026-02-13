# -*- coding: utf-8 -*-
from odoo import models, fields, tools


class CapaciteCharge(models.Model):
    _name = 'mrp.capacite.charge'
    _auto = False
    _description = 'Capacité vs Charge par poste de travail'
    _order = 'date asc, workcenter_name asc'

    date = fields.Date(string='Date', readonly=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string='Poste de travail', readonly=True)
    workcenter_name = fields.Char(string='Poste', readonly=True)
    capacite_heures = fields.Float(string='Capacité (h)', digits=(10, 2), readonly=True)
    charge_heures = fields.Float(string='Charge restante (h)', digits=(10, 2), readonly=True)
    nb_operations = fields.Integer(string='Nb opérations', readonly=True)
    taux_charge = fields.Float(string='Taux charge (%)', digits=(10, 1), readonly=True)
    solde_heures = fields.Float(string='Solde (h)', digits=(10, 2), readonly=True)

    def _get_name_expr(self, alias, col='name'):
        """
        Retourne une expression SQL compatible varchar ET jsonb.
        - Si varchar  → cast direct en text
        - Si jsonb    → extraction fr_FR puis en_US puis cast brut
        On détecte le type réel de la colonne au moment de l'init.
        """
        cr = self.env.cr
        cr.execute("""
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
            LIMIT 1
        """, (alias, col))
        row = cr.fetchone()
        dtype = row[0] if row else 'character varying'
        if dtype == 'jsonb':
            return (
                f"COALESCE({alias}.{col}->>'fr_FR', "
                f"{alias}.{col}->>'en_US', "
                f"{alias}.{col}::text)"
            )
        else:
            return f"{alias}.{col}::text"

    def init(self):
        tools.drop_view_if_exists(self.env.cr, 'mrp_capacite_charge')

        wc_name  = self._get_name_expr('mrp_workcenter')
        pr_name  = self._get_name_expr('planning_role')

        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW mrp_capacite_charge AS (

            WITH charge AS (
                SELECT
                    wo.workcenter_id,
                    {wc_name}                                    AS workcenter_name,
                    DATE(wo.date_start)                          AS date,
                    COUNT(*)                                     AS nb_operations,
                    SUM(
                        CASE
                            WHEN wo.state IN ('pending', 'ready', 'waiting')
                                THEN COALESCE(wo.duration_expected, 0) / 60.0
                            ELSE
                                GREATEST(
                                    COALESCE(wo.duration_expected, 0)
                                    - COALESCE(wo.duration, 0), 0
                                ) / 60.0
                        END
                    )                                            AS charge_heures
                FROM mrp_workorder wo
                JOIN mrp_workcenter ON mrp_workcenter.id = wo.workcenter_id
                WHERE wo.state NOT IN ('done', 'cancel')
                  AND wo.date_start IS NOT NULL
                GROUP BY
                    wo.workcenter_id,
                    {wc_name},
                    DATE(wo.date_start)
            ),

            capacite AS (
                SELECT
                    mrp_workcenter.id                            AS workcenter_id,
                    {wc_name}                                    AS workcenter_name,
                    DATE(ps.start_datetime)                      AS date,
                    SUM(
                        EXTRACT(EPOCH FROM (
                            ps.end_datetime - ps.start_datetime
                        )) / 3600.0
                    )                                            AS capacite_heures
                FROM planning_slot ps
                JOIN planning_role ON planning_role.id = ps.role_id
                JOIN mrp_workcenter ON LOWER(TRIM({wc_name})) = LOWER(TRIM({pr_name}))
                WHERE ps.state = 'published'
                GROUP BY
                    mrp_workcenter.id,
                    {wc_name},
                    DATE(ps.start_datetime)
            ),

            all_keys AS (
                SELECT workcenter_id, workcenter_name, date FROM charge
                UNION
                SELECT workcenter_id, workcenter_name, date FROM capacite
            )

            SELECT
                ROW_NUMBER() OVER (
                    ORDER BY ak.date, ak.workcenter_name
                )                                               AS id,
                ak.workcenter_id,
                ak.workcenter_name,
                ak.date,
                COALESCE(cap.capacite_heures, 0)               AS capacite_heures,
                COALESCE(ch.charge_heures,   0)                AS charge_heures,
                COALESCE(ch.nb_operations,   0)                AS nb_operations,
                COALESCE(ch.charge_heures, 0)
                    - COALESCE(cap.capacite_heures, 0)         AS solde_heures,
                CASE
                    WHEN COALESCE(cap.capacite_heures, 0) > 0
                        THEN ROUND(
                            (COALESCE(ch.charge_heures, 0)
                             / cap.capacite_heures * 100.0
                            )::numeric, 1
                        )
                    WHEN COALESCE(ch.charge_heures, 0) > 0
                        THEN 999
                    ELSE 0
                END                                             AS taux_charge

            FROM all_keys ak
            LEFT JOIN charge   ch  ON ch.workcenter_id  = ak.workcenter_id
                                   AND ch.date           = ak.date
            LEFT JOIN capacite cap ON cap.workcenter_id  = ak.workcenter_id
                                   AND cap.date          = ak.date
        )
        """)
