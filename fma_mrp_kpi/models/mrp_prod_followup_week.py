# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools


class MrpProdFollowupWeek(models.Model):
    _name = "mrp.prod.followup.week"
    _description = "Suivi Production charge vs capacité"
    _auto = False
    _rec_name = "week_label"
    _order = "month_start desc, week_start desc, workcenter_name asc"

    atelier_label = fields.Char(string="Atelier", readonly=True)
    month_start = fields.Date(string="Mois", readonly=True)
    month_label = fields.Char(string="Mois", readonly=True)
    week_start = fields.Date(string="Début semaine", readonly=True)
    week_label = fields.Char(string="Semaine", readonly=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string="Poste de travail", readonly=True)
    workcenter_name = fields.Char(string="Poste de travail", readonly=True)
    capacite_heures = fields.Float(string="Capacité (h)", digits=(10, 2), readonly=True)
    charge_prevue_heures = fields.Float(string="Charge prévue (h)", digits=(10, 2), readonly=True)
    charge_effectuee_heures = fields.Float(string="Charge effectuée (h)", digits=(10, 2), readonly=True)
    ecart_heures = fields.Float(string="Écart capacité - charge (h)", digits=(10, 2), readonly=True)
    taux_charge = fields.Float(string="Taux (%)", digits=(10, 1), readonly=True)
    nb_operations = fields.Integer(string="# Ops", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                WITH weekly_poste AS (
                    SELECT
                        date_trunc('month', c.date)::date AS month_start,
                        date_trunc('week', c.date)::date AS week_start,
                        c.workcenter_id,
                        c.workcenter_name,
                        SUM(COALESCE(c.capacite_heures, 0)) AS capacite_heures,
                        SUM(COALESCE(c.charge_prevue_jour, 0)) AS charge_prevue_heures,
                        SUM(COALESCE(c.charge_effectuee_jour, 0)) AS charge_effectuee_heures,
                        SUM(COALESCE(c.nb_operations, 0)) AS nb_operations
                    FROM mrp_capacite_charge c
                    GROUP BY date_trunc('month', c.date)::date,
                             date_trunc('week', c.date)::date,
                             c.workcenter_id,
                             c.workcenter_name
                )
                SELECT
                    ROW_NUMBER() OVER (ORDER BY month_start DESC, week_start DESC, COALESCE(workcenter_name, '')) AS id,
                    'Atelier'::varchar AS atelier_label,
                    month_start,
                    to_char(month_start, 'MM/YYYY') AS month_label,
                    week_start,
                    to_char(week_start, '"W"IW YYYY') AS week_label,
                    workcenter_id,
                    workcenter_name,
                    ROUND(capacite_heures::numeric, 2) AS capacite_heures,
                    ROUND(charge_prevue_heures::numeric, 2) AS charge_prevue_heures,
                    ROUND(charge_effectuee_heures::numeric, 2) AS charge_effectuee_heures,
                    ROUND((capacite_heures - charge_prevue_heures)::numeric, 2) AS ecart_heures,
                    CASE
                        WHEN capacite_heures > 0 THEN ROUND(((charge_prevue_heures / capacite_heures) * 100.0)::numeric, 1)
                        WHEN charge_prevue_heures > 0 THEN 999
                        ELSE 0
                    END AS taux_charge,
                    nb_operations
                FROM weekly_poste
            )
        """)

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        res = super().read_group(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
        for row in res:
            capacite = float(row.get('capacite_heures') or 0.0)
            charge = float(row.get('charge_prevue_heures') or 0.0)
            effectue = float(row.get('charge_effectuee_heures') or 0.0)
            row['ecart_heures'] = round(capacite - charge, 2)
            if capacite > 0:
                row['taux_charge'] = round((charge / capacite) * 100.0, 1)
            elif charge > 0:
                row['taux_charge'] = 999.0
            else:
                row['taux_charge'] = 0.0
            # keep for completeness when group rows don't expose raw computed values
            row['charge_effectuee_heures'] = round(effectue, 2)
        return res
