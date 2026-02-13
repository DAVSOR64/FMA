# -*- coding: utf-8 -*-
from odoo import models, fields, tools
import logging
import traceback
import pytz

_logger = logging.getLogger(__name__)


class PlanningRole(models.Model):
    _inherit = 'planning.role'

    workcenter_id = fields.Many2one(
        'mrp.workcenter',
        string='Poste de travail lié',
        help='Lier ce rôle Planning au poste de travail pour le calcul de capacité',
    )


class CapaciteCache(models.Model):
    _name = 'mrp.capacite.cache'
    _description = 'Cache capacité planning par poste/jour'
    _auto = True

    workcenter_id = fields.Many2one('mrp.workcenter', string='Poste', index=True, ondelete='cascade')
    workcenter_name = fields.Char(string='Nom poste')
    date = fields.Date(string='Date', index=True)
    capacite_heures = fields.Float(string='Capacité (h)', digits=(10, 2))

    def _to_utc(self, dt):
        if dt is None:
            return dt
        if dt.tzinfo is None:
            return pytz.utc.localize(dt)
        return dt.astimezone(pytz.utc)

    def refresh(self):
        self.search([]).unlink()
        slots = self.env['planning.slot'].search([('state', '=', 'published')])
        _logger.info('REFRESH CAPACITE : %d slots publiés', len(slots))
        if not slots:
            return
        vals_list = []
        for slot in slots:
            if not slot.resource_id or not slot.role_id:
                continue
            workcenter = slot.role_id.workcenter_id
            if not workcenter:
                continue
            calendar = slot.resource_id.calendar_id
            if not calendar:
                delta = (slot.end_datetime - slot.start_datetime).total_seconds() / 3600.0
                vals_list.append({
                    'workcenter_id': workcenter.id,
                    'workcenter_name': workcenter.name,
                    'date': slot.start_datetime.date(),
                    'capacite_heures': delta,
                })
                continue
            try:
                date_start = self._to_utc(slot.start_datetime)
                date_stop = self._to_utc(slot.end_datetime)
                intervals = calendar._work_intervals_batch(date_start, date_stop, resources=slot.resource_id)
                resource_intervals = intervals.get(slot.resource_id.id, [])
                heures_par_jour = {}
                for start, stop, _meta in resource_intervals:
                    jour = start.date()
                    duree = (stop - start).total_seconds() / 3600.0
                    heures_par_jour[jour] = heures_par_jour.get(jour, 0) + duree
                for jour, heures in heures_par_jour.items():
                    if heures > 0:
                        vals_list.append({
                            'workcenter_id': workcenter.id,
                            'workcenter_name': workcenter.name,
                            'date': jour,
                            'capacite_heures': heures,
                        })
            except Exception as e:
                _logger.error('Erreur slot %s : %s\n%s', slot.id, e, traceback.format_exc())
        aggregated = {}
        for v in vals_list:
            key = (v['workcenter_id'], str(v['date']))
            if key in aggregated:
                aggregated[key]['capacite_heures'] += v['capacite_heures']
            else:
                aggregated[key] = v.copy()
        if aggregated:
            self.create(list(aggregated.values()))
        _logger.info('REFRESH TERMINÉ : %d entrées créées', len(aggregated))


class CapaciteRefreshWizard(models.TransientModel):
    _name = 'mrp.capacite.refresh.wizard'
    _description = 'Wizard recalcul capacité'

    nb_slots = fields.Integer(string='Slots publiés', readonly=True)
    nb_entries = fields.Integer(string='Entrées calculées', readonly=True)
    message = fields.Char(string='Résultat', readonly=True)

    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        res['nb_slots'] = self.env['planning.slot'].search_count([('state', '=', 'published')])
        return res

    def action_refresh(self):
        self.env['mrp.capacite.cache'].refresh()
        nb = self.env['mrp.capacite.cache'].search_count([])
        self.write({
            'nb_entries': nb,
            'message': '%d entrées calculées depuis %d slots publiés' % (nb, self.nb_slots),
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class CapaciteChargeDetail(models.Model):
    _name = 'mrp.capacite.charge.detail'
    _auto = False
    _description = 'Détail opérations par poste/jour'
    _order = 'date asc, workcenter_name asc'

    date = fields.Date(string='Date', readonly=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string='Poste', readonly=True)
    workcenter_name = fields.Char(string='Poste', readonly=True)
    production_id = fields.Many2one('mrp.production', string='OF', readonly=True)
    production_name = fields.Char(string='N° OF', readonly=True)
    sale_order_id = fields.Many2one('sale.order', string='Commande', readonly=True)
    sale_order_name = fields.Char(string='N° Commande', readonly=True)
    projet = fields.Char(string='Projet', readonly=True)
    operation_name = fields.Char(string='Opération', readonly=True)
    duration_expected = fields.Float(string='Prévu (h)', digits=(10, 2), readonly=True)
    duration_done = fields.Float(string='Réalisé (h)', digits=(10, 2), readonly=True)
    charge_restante = fields.Float(string='Restant (h)', digits=(10, 2), readonly=True)
    state = fields.Char(string='Statut', readonly=True)

    def _get_sale_col(self):
        """Détecte le nom du champ liant mrp.production à sale.order."""
        self.env.cr.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'mrp_production'
            AND column_name IN ('sale_id', 'x_sale_id', 'procurement_sale_id', 'x_studio_mtn_mrp_sale_order')
            LIMIT 1
        """)
        row = self.env.cr.fetchone()
        return row[0] if row else None

    def _get_name_expr(self, table, col='name'):
        self.env.cr.execute("""
            SELECT data_type FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s LIMIT 1
        """, (table, col))
        row = self.env.cr.fetchone()
        dtype = row[0] if row else 'character varying'
        if dtype == 'jsonb':
            return (f"COALESCE({table}.{col}->>'fr_FR', "
                    f"{table}.{col}->>'en_US', {table}.{col}::text)")
        return f"{table}.{col}::text"

    def init(self):
        tools.drop_view_if_exists(self.env.cr, 'mrp_capacite_charge_detail')
        wc_name = self._get_name_expr('mrp_workcenter')
        sale_col = self._get_sale_col()

        # Vérifier si x_studio_projet existe
        self.env.cr.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'sale_order' AND column_name = 'x_studio_projet'
        """)
        has_projet = bool(self.env.cr.fetchone())

        if sale_col:
            sale_join = f"LEFT JOIN sale_order so ON so.id = mp.{sale_col}"
            sale_id_expr = f"mp.{sale_col} AS sale_order_id,"
            sale_name_expr = "so.name AS sale_order_name,"
            projet_expr = "so.x_studio_projet.name::text AS projet," if has_projet else "NULL::text AS projet,"
        else:
            sale_join = ""
            sale_id_expr = "NULL::integer AS sale_order_id,"
            sale_name_expr = "NULL::text AS sale_order_name,"
            projet_expr = "NULL::text AS projet,"

        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW mrp_capacite_charge_detail AS (
            SELECT
                wo.id                                       AS id,
                DATE(wo.date_start)                         AS date,
                wo.workcenter_id,
                {wc_name}                                   AS workcenter_name,
                wo.production_id,
                mp.name                                     AS production_name,
                {sale_id_expr}
                {sale_name_expr}
                {projet_expr}
                wo.name                                     AS operation_name,
                COALESCE(wo.duration_expected, 0) / 60.0   AS duration_expected,
                COALESCE(wo.duration, 0) / 60.0             AS duration_done,
                CASE
                    WHEN wo.state IN ('pending', 'ready', 'waiting')
                        THEN COALESCE(wo.duration_expected, 0) / 60.0
                    ELSE GREATEST(
                        COALESCE(wo.duration_expected, 0)
                        - COALESCE(wo.duration, 0), 0
                    ) / 60.0
                END                                         AS charge_restante,
                wo.state
            FROM mrp_workorder wo
            JOIN mrp_workcenter ON mrp_workcenter.id = wo.workcenter_id
            JOIN mrp_production mp ON mp.id = wo.production_id
            {sale_join}
            WHERE wo.state NOT IN ('done', 'cancel')
              AND wo.date_start IS NOT NULL
        )
        """)


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
    projets = fields.Char(string='Projets', readonly=True)

    def _get_sale_col(self):
        self.env.cr.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'mrp_production'
            AND column_name IN ('sale_id', 'x_sale_id', 'procurement_sale_id', 'x_studio_mtn_mrp_sale_order')
            LIMIT 1
        """)
        row = self.env.cr.fetchone()
        return row[0] if row else None

    def _get_name_expr(self, table, col='name'):
        self.env.cr.execute("""
            SELECT data_type FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s LIMIT 1
        """, (table, col))
        row = self.env.cr.fetchone()
        dtype = row[0] if row else 'character varying'
        if dtype == 'jsonb':
            return (f"COALESCE({table}.{col}->>'fr_FR', "
                    f"{table}.{col}->>'en_US', {table}.{col}::text)")
        return f"{table}.{col}::text"

    def action_voir_detail(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Détail — %s %s' % (self.workcenter_name, self.date),
            'res_model': 'mrp.capacite.charge.detail',
            'view_mode': 'tree',
            'domain': [
                ('workcenter_id', '=', self.workcenter_id.id),
                ('date', '=', str(self.date)),
            ],
            'target': 'new',
        }

    def init(self):
        tools.drop_view_if_exists(self.env.cr, 'mrp_capacite_charge')
        wc_name = self._get_name_expr('mrp_workcenter')
        sale_col = self._get_sale_col()

        self.env.cr.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'sale_order' AND column_name = 'x_studio_projet'
        """)
        has_projet = bool(self.env.cr.fetchone())

        if sale_col and has_projet:
            sale_join = f"LEFT JOIN sale_order so ON so.id = mp.{sale_col}"
            projet_agg = "STRING_AGG(DISTINCT so.x_studio_projet::text, ', ') AS projets,"
        else:
            sale_join = ""
            projet_agg = "NULL::text AS projets,"

        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW mrp_capacite_charge AS (
            WITH charge AS (
                SELECT
                    wo.workcenter_id,
                    {wc_name}                                   AS workcenter_name,
                    DATE(wo.date_start)                         AS date,
                    COUNT(*)                                    AS nb_operations,
                    {projet_agg}
                    SUM(
                        CASE
                            WHEN wo.state IN ('pending', 'ready', 'waiting')
                                THEN COALESCE(wo.duration_expected, 0) / 60.0
                            ELSE GREATEST(
                                COALESCE(wo.duration_expected, 0)
                                - COALESCE(wo.duration, 0), 0
                            ) / 60.0
                        END
                    )                                           AS charge_heures
                FROM mrp_workorder wo
                JOIN mrp_workcenter ON mrp_workcenter.id = wo.workcenter_id
                JOIN mrp_production mp ON mp.id = wo.production_id
                {sale_join}
                WHERE wo.state NOT IN ('done', 'cancel')
                  AND wo.date_start IS NOT NULL
                GROUP BY wo.workcenter_id, {wc_name}, DATE(wo.date_start)
            ),
            capacite AS (
                SELECT workcenter_id, workcenter_name, date,
                       SUM(capacite_heures) AS capacite_heures
                FROM mrp_capacite_cache
                GROUP BY workcenter_id, workcenter_name, date
            ),
            all_keys AS (
                SELECT workcenter_id, workcenter_name, date FROM charge
                UNION
                SELECT workcenter_id, workcenter_name, date FROM capacite
            )
            SELECT
                ROW_NUMBER() OVER (ORDER BY ak.date, ak.workcenter_name) AS id,
                ak.workcenter_id, ak.workcenter_name, ak.date,
                COALESCE(cap.capacite_heures, 0)       AS capacite_heures,
                COALESCE(ch.charge_heures, 0)          AS charge_heures,
                COALESCE(ch.nb_operations, 0)          AS nb_operations,
                COALESCE(ch.projets, '')                AS projets,
                COALESCE(ch.charge_heures, 0) - COALESCE(cap.capacite_heures, 0) AS solde_heures,
                CASE
                    WHEN COALESCE(cap.capacite_heures, 0) > 0
                        THEN ROUND(((COALESCE(ch.charge_heures, 0) / cap.capacite_heures) * 100.0)::numeric, 1)
                    WHEN COALESCE(ch.charge_heures, 0) > 0 THEN 999
                    ELSE 0
                END AS taux_charge
            FROM all_keys ak
            LEFT JOIN charge   ch  ON ch.workcenter_id  = ak.workcenter_id AND ch.date = ak.date
            LEFT JOIN capacite cap ON cap.workcenter_id = ak.workcenter_id AND cap.date = ak.date
        )
        """)
