# -*- coding: utf-8 -*-
from odoo import models, fields, tools
from psycopg2 import sql


class MRPPlanningAnalysisReport(models.Model):
    _name = "mrp.planning.analysis.report"
    _description = "Manufacture Planning Analysis Report"
    _auto = False

    resource_id = fields.Many2one("resource.resource", string="Resource", readonly=True)
    workcenter_id = fields.Many2one("mrp.workcenter", string="Poste de travail", readonly=True)
    x_studio_projet_so = fields.Many2one("project.project", string="Projet SO", readonly=True)
    day = fields.Date("Jour", readonly=True)
    availability = fields.Float("Disponibilité (h)", readonly=True)
    needed = fields.Float("Besoin (h)", readonly=True)
    is_shortage = fields.Float("Écart (Dispo - Besoin)", readonly=True)

    @property
    def _table_query(self):
        return """
        WITH RECURSIVE base AS (
            SELECT
                mw.workcenter_id,
                mp.x_studio_projet_so,
                mw.date_macro::date AS day,
                ROUND((mw.duration_expected::numeric / 60)) AS total_needed
            FROM mrp_workorder mw
            INNER JOIN mrp_production mp ON mp.id = mw.production_id
        ),
        splitted AS (
            SELECT
                workcenter_id,
                x_studio_projet_so,
                day,
                CASE WHEN total_needed > 8 THEN 8 ELSE total_needed END AS needed,
                CASE WHEN total_needed > 8 THEN total_needed - 8 ELSE 0 END AS remaining
            FROM base
            UNION ALL
            SELECT
                workcenter_id,
                x_studio_projet_so,
                day + 1,
                CASE WHEN remaining > 8 THEN 8 ELSE remaining END AS needed,
                CASE WHEN remaining > 8 THEN remaining - 8 ELSE 0 END AS remaining
            FROM splitted
            WHERE remaining > 0
        ),
        merged AS (
            SELECT
                ps.resource_id,
                splitted.workcenter_id,
                splitted.x_studio_projet_so,
                splitted.day,
                8 AS availability,
                splitted.needed
            FROM splitted
            LEFT JOIN planning_slot_day ps
                ON ps.workcenter_id = splitted.workcenter_id
                AND ps.day = splitted.day
        )
        SELECT
            row_number() OVER () AS id,
            m.resource_id,
            m.workcenter_id,
            m.x_studio_projet_so,
            m.day,
            SUM(m.availability) AS availability,
            SUM(m.needed) AS needed,
            SUM(m.availability) - SUM(m.needed) AS is_shortage
        FROM merged m
        GROUP BY m.resource_id, m.workcenter_id, m.x_studio_projet_so, m.day
        ORDER BY m.day
        """

    def init(self):
        # Création de la vue planning_slot_day
        self.env.cr.execute('''
            CREATE OR REPLACE VIEW planning_slot_day AS (
                SELECT
                    ps.resource_id,
                    ps.workcenter_id,
                    gs.day::date AS day,
                    8 AS availability,
                    0 AS needed
                FROM planning_slot ps
                JOIN LATERAL generate_series(
                    ps.start_datetime::date,
                    ps.end_datetime::date,
                    INTERVAL '1 day'
                ) AS gs(day) ON TRUE
                WHERE ps.workcenter_id IS NOT NULL
            )
        ''')

        # Création de la vue principale
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            sql.SQL("CREATE OR REPLACE VIEW {} AS ({})").format(
                sql.Identifier(self._table),
                sql.SQL(self._table_query),
            )
        )
