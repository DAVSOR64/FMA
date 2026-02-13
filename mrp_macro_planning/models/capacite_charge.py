# -*- coding: utf-8 -*-
from odoo import models, fields, tools


class CapaciteCharge(models.Model):
    _name = 'mrp.capacite.charge'
    _auto = False
    _description = 'Capacité vs Charge par poste de travail'
    _order = 'date asc, workcenter_name asc'

    # --- Dimensions ---
    date = fields.Date(string='Date', readonly=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string='Poste de travail', readonly=True)
    workcenter_name = fields.Char(string='Poste', readonly=True)

    # --- Capacité (depuis planning.slot) ---
    capacite_heures = fields.Float(string='Capacité (h)', digits=(10, 2), readonly=True)

    # --- Charge (depuis mrp.workorder) ---
    charge_heures = fields.Float(string='Charge restante (h)', digits=(10, 2), readonly=True)
    nb_operations = fields.Integer(string='Nb opérations', readonly=True)

    # --- Indicateur ---
    taux_charge = fields.Float(string='Taux charge (%)', digits=(10, 1), readonly=True)
    solde_heures = fields.Float(string='Solde (h)', digits=(10, 2), readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, 'mrp_capacite_charge')
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW mrp_capacite_charge AS (

            -- ============================================================
            -- CHARGE : durée restante par workcenter par jour
            -- Si state = 'ready' (pas commencé) → duration_expected
            -- Sinon → MAX(0, duration_expected - duration)
            -- ============================================================
            WITH charge AS (
                SELECT
                    wo.workcenter_id,
                    wc.name                                      AS workcenter_name,
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
                JOIN mrp_workcenter wc ON wc.id = wo.workcenter_id
                WHERE wo.state NOT IN ('done', 'cancel')
                  AND wo.date_start IS NOT NULL
                GROUP BY wo.workcenter_id, wc.name, DATE(wo.date_start)
            ),

            -- ============================================================
            -- CAPACITÉ : heures planifiées par role (= workcenter) par jour
            -- On joint planning.role sur le nom du workcenter
            -- La capacité = somme des durées des slots (end - start) en heures
            -- ============================================================
            capacite AS (
                SELECT
                    wc.id                                        AS workcenter_id,
                    wc.name                                      AS workcenter_name,
                    DATE(ps.start_datetime)                      AS date,
                    SUM(
                        EXTRACT(EPOCH FROM (
                            ps.end_datetime - ps.start_datetime
                        )) / 3600.0
                    )                                            AS capacite_heures
                FROM planning_slot ps
                JOIN planning_role pr  ON pr.id = ps.role_id
                JOIN mrp_workcenter wc ON LOWER(TRIM(wc.name)) = LOWER(TRIM(pr.name))
                WHERE ps.state = 'published'
                GROUP BY wc.id, wc.name, DATE(ps.start_datetime)
            ),

            -- ============================================================
            -- UNION des dates/postes connus (charge OU capacité)
            -- ============================================================
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
                        THEN 999   -- charge sans capacité définie
                    ELSE 0
                END                                             AS taux_charge

            FROM all_keys ak
            LEFT JOIN charge   ch  ON ch.workcenter_id  = ak.workcenter_id
                                   AND ch.date           = ak.date
            LEFT JOIN capacite cap ON cap.workcenter_id  = ak.workcenter_id
                                   AND cap.date          = ak.date
        )
        """)
