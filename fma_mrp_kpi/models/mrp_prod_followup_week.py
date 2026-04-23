# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class MrpProdFollowupWeek(models.Model):
    _name = "mrp.prod.followup.week"
    _description = "Suivi Production hebdomadaire"
    _auto = False
    _order = "week_start desc, scope asc, workcenter_name asc"

    week_start = fields.Date(string="Semaine du", readonly=True)
    week_label = fields.Char(string="Semaine", readonly=True)
    scope = fields.Selection([
        ('atelier', 'Atelier'),
        ('poste', 'Poste'),
    ], string="Niveau", readonly=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string="Poste de travail", readonly=True)
    workcenter_name = fields.Char(string="Poste de travail", readonly=True)
    capacite_semaine = fields.Float(string="Capacité semaine (h)", digits=(10, 2), readonly=True)
    charge_prevue_semaine = fields.Float(string="Charge prévue semaine (h)", digits=(10, 2), readonly=True)
    charge_effectuee_semaine = fields.Float(string="Charge effectuée semaine (h)", digits=(10, 2), readonly=True)
    ecart_heures = fields.Float(string="Écart capacité - charge (h)", digits=(10, 2), readonly=True)
    taux_charge = fields.Float(string="Taux charge (%)", digits=(10, 1), readonly=True)
    nb_operations = fields.Integer(string="# Ops", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                WITH weekly_poste AS (
                    SELECT
                        date_trunc('week', c.date)::date AS week_start,
                        c.workcenter_id,
                        c.workcenter_name,
                        SUM(COALESCE(c.capacite_heures, 0)) AS capacite_semaine,
                        SUM(COALESCE(c.charge_prevue_jour, 0)) AS charge_prevue_semaine,
                        SUM(COALESCE(c.charge_effectuee_jour, 0)) AS charge_effectuee_semaine,
                        SUM(COALESCE(c.nb_operations, 0)) AS nb_operations
                    FROM mrp_capacite_charge c
                    GROUP BY date_trunc('week', c.date)::date, c.workcenter_id, c.workcenter_name
                ),
                weekly_all AS (
                    SELECT
                        week_start,
                        'atelier'::varchar AS scope,
                        NULL::integer AS workcenter_id,
                        'ATELIER'::varchar AS workcenter_name,
                        SUM(capacite_semaine) AS capacite_semaine,
                        SUM(charge_prevue_semaine) AS charge_prevue_semaine,
                        SUM(charge_effectuee_semaine) AS charge_effectuee_semaine,
                        SUM(nb_operations) AS nb_operations
                    FROM weekly_poste
                    GROUP BY week_start
                    UNION ALL
                    SELECT
                        week_start,
                        'poste'::varchar AS scope,
                        workcenter_id,
                        workcenter_name,
                        capacite_semaine,
                        charge_prevue_semaine,
                        charge_effectuee_semaine,
                        nb_operations
                    FROM weekly_poste
                )
                SELECT
                    ROW_NUMBER() OVER (ORDER BY week_start DESC, scope, COALESCE(workcenter_name, '')) AS id,
                    week_start,
                    to_char(week_start, '"W"IW YYYY') AS week_label,
                    scope,
                    workcenter_id,
                    workcenter_name,
                    ROUND(capacite_semaine::numeric, 2) AS capacite_semaine,
                    ROUND(charge_prevue_semaine::numeric, 2) AS charge_prevue_semaine,
                    ROUND(charge_effectuee_semaine::numeric, 2) AS charge_effectuee_semaine,
                    ROUND((capacite_semaine - charge_prevue_semaine)::numeric, 2) AS ecart_heures,
                    CASE
                        WHEN capacite_semaine > 0
                            THEN ROUND(((charge_prevue_semaine / capacite_semaine) * 100.0)::numeric, 1)
                        WHEN charge_prevue_semaine > 0 THEN 999
                        ELSE 0
                    END AS taux_charge,
                    nb_operations
                FROM weekly_all
            )
        """)
