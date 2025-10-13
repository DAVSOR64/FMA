# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, tools
from odoo import fields, models

from psycopg2 import sql

class MRPPlanningAnalysisReport(models.Model):
    _name = "mrp.planning.analysis.report"
    _description = "Manufacture Planning Analysis Report"
    _auto = False

    resource_id = fields.Many2one("resource.resource", string="Resource", readonly=True)
    workcenter_id = fields.Many2one("mrp.workcenter", string="Workcenter")
    x_studio_projet_so = fields.Many2one("project.project", string="MTN Projet SO")
    day = fields.Date("Day", readonly=True)
    availability = fields.Integer('Availability', readonly=True, group_operator="sum")
    needed = fields.Integer('Needed', readonly=True, group_operator="sum")
    is_shortage = fields.Integer(
        string='Shortage',
        compute='_compute_is_shortage_grouped',
        store=False
    )

    def _compute_is_shortage_grouped(self):
        for record in self:
            # record.availability et record.needed contiendront les valeurs agrégées si read_group
            record.is_shortage = record.availability - record.needed
            # record.is_shortage = (record.availability or 0) < (record.needed or 0)

    @property
    def _table_query(self):
        return """
        WITH RECURSIVE base AS (
          SELECT
            mw.workcenter_id,
            mp.x_studio_projet_so,
            mw.date_macro::date AS day,
            ROUND((mw.duration_expected::numeric / 60)) AS total_needed
          FROM mrp_workorder mw inner join mrp_production mp on mp.id = mw.production_id
        ),
        splitted AS (
          -- ligne initiale
          SELECT
            workcenter_id,
            x_studio_projet_so,
            day,
            CASE WHEN total_needed > 8 THEN 8 ELSE total_needed END AS needed,
            CASE WHEN total_needed > 8 THEN total_needed - 8 ELSE 0 END AS remaining
          FROM base
        
          UNION ALL
        
          -- lignes suivantes tant qu'il reste > 0
          SELECT
            workcenter_id,
            x_studio_projet_so,
            day + 1,
            CASE WHEN remaining > 8 THEN 8 ELSE remaining END AS needed,
            CASE WHEN remaining > 8 THEN remaining - 8 ELSE 0 END AS remaining
          FROM splitted
          WHERE remaining > 0
        )
        SELECT
          row_number() OVER (PARTITION BY splitted.workcenter_id, splitted.x_studio_projet_so ORDER BY splitted.day) AS id,
          ps.resource_id,
          splitted.workcenter_id,
          splitted.x_studio_projet_so,
          splitted.day,
          CASE WHEN ps.resource_id IS NOT NULL THEN 8 ELSE 0 END AS availability,
          splitted.needed
        FROM splitted
        FULL OUTER JOIN mrp_workorder mo ON mo.workcenter_id = splitted.workcenter_id
        FULL OUTER JOIN planning_slot_day ps ON ps.workcenter_id = splitted.workcenter_id  AND ps.day = splitted.day
        WHERE mo.state not in ('done', 'cancel')
        ORDER BY splitted.workcenter_id, splitted.x_studio_projet_so, splitted.day
        """

    def init(self):
        self.env.cr.execute('''
                            CREATE OR REPLACE VIEW planning_slot_day AS (
                            SELECT
                                ps.resource_id,
                                ps.workcenter_id,
                                gs.day::date AS day,
                                8 AS availability,
                                0 AS Needed
                            FROM planning_slot ps
                                JOIN LATERAL generate_series(
                                ps.start_datetime::date,
                                ps.end_datetime::date,
                                INTERVAL '1 day'
                            ) AS gs(day) ON TRUE
                            WHERE ps.workcenter_id IS NOT NULL)''')
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            sql.SQL("CREATE or REPLACE VIEW {} as ({})").format(
                sql.Identifier(self._table),
                sql.SQL(self._table_query)
            )
        )
