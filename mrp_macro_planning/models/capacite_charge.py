# -*- coding: utf-8 -*-
from odoo import models, fields, tools, api
import logging
import traceback
import pytz
from datetime import timedelta

_logger = logging.getLogger(__name__)


class PlanningRole(models.Model):
    _inherit = 'planning.role'

    workcenter_id = fields.Many2one(
        'mrp.workcenter',
        string='Poste de travail lié',
        help='Lier ce rôle Planning au poste de travail pour le calcul de capacité',
    )


# ─────────────────────────────────────────────────────────────────────────────
# Cache CAPACITE (depuis Planning)
# ─────────────────────────────────────────────────────────────────────────────

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
        """Recalcule la capacité depuis les slots Planning publiés"""
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
        
        # Agréger par workcenter_id + date
        aggregated = {}
        for v in vals_list:
            key = (v['workcenter_id'], str(v['date']))
            if key in aggregated:
                aggregated[key]['capacite_heures'] += v['capacite_heures']
            else:
                aggregated[key] = v.copy()
        
        if aggregated:
            self.create(list(aggregated.values()))
        _logger.info('REFRESH CAPACITE TERMINÉ : %d entrées', len(aggregated))


# ─────────────────────────────────────────────────────────────────────────────
# Cache CHARGE (depuis Workorders)
# ─────────────────────────────────────────────────────────────────────────────

class WorkorderChargeCache(models.Model):
    _name = 'mrp.workorder.charge.cache'
    _description = 'Cache charge workorder répartie par jour'
    _auto = True

    workorder_id = fields.Many2one('mrp.workorder', string='Ordre de travail', index=True, ondelete='cascade')
    workcenter_id = fields.Many2one('mrp.workcenter', string='Poste', index=True, ondelete='cascade')
    workcenter_name = fields.Char(string='Nom poste')
    date = fields.Date(string='Date', index=True)
    charge_heures = fields.Float(string='Charge (h)', digits=(10, 2))
    employee_ids = fields.Many2many('hr.employee', string='Opérateurs')

    def _to_utc(self, dt):
        if dt is None:
            return dt
        if dt.tzinfo is None:
            return pytz.utc.localize(dt)
        return dt.astimezone(pytz.utc)

    def refresh(self):
        """Recalcule la charge depuis les workorders actifs"""
        self.search([]).unlink()
        
        workorders = self.env['mrp.workorder'].search([
            ('state', 'not in', ('done', 'cancel')),
            ('date_start', '!=', False)
        ])
        
        _logger.info('REFRESH CHARGE : %d workorders actifs', len(workorders))
        if not workorders:
            return
        
        vals_list = []
        for wo in workorders:
            if not wo.workcenter_id or not wo.date_start:
                continue
            
            # Charge restante en heures
            if wo.state in ('pending', 'ready', 'waiting'):
                charge_restante_minutes = wo.duration_expected or 0
            else:
                charge_restante_minutes = max((wo.duration_expected or 0) - (wo.duration or 0), 0)
            
            if charge_restante_minutes <= 0:
                continue
            
            charge_restante_heures = charge_restante_minutes / 60.0
            
            # Récupérer les opérateurs assignés
            employee_ids = self.env['mrp.workcenter.productivity'].search([
                ('workorder_id', '=', wo.id),
                ('employee_id', '!=', False)
            ]).mapped('employee_id').ids
            
            # Calendrier du workcenter
            calendar = wo.workcenter_id.calendar_id
            
            if not calendar:
                # Pas de calendrier → tout sur date_start
                vals_list.append({
                    'workorder_id': wo.id,
                    'workcenter_id': wo.workcenter_id.id,
                    'workcenter_name': wo.workcenter_id.name,
                    'date': wo.date_start.date(),
                    'charge_heures': charge_restante_heures,
                    'employee_ids': [(6, 0, employee_ids)],
                })
                continue
            
            # Calculer la date de fin prévue
            if wo.date_planned_finished:
                date_end = wo.date_planned_finished
            else:
                # Estimer date_end = date_start + duration_expected
                date_end = wo.date_start + timedelta(minutes=wo.duration_expected or 0)
            
            try:
                date_start_utc = self._to_utc(wo.date_start)
                date_end_utc = self._to_utc(date_end)
                
                # Récupérer les intervalles de travail
                intervals = calendar._work_intervals_batch(date_start_utc, date_end_utc)
                work_intervals = intervals.get(False, [])  # calendar sans resource_id
                
                if not work_intervals:
                    # Fallback : tout sur date_start
                    vals_list.append({
                        'workorder_id': wo.id,
                        'workcenter_id': wo.workcenter_id.id,
                        'workcenter_name': wo.workcenter_id.name,
                        'date': wo.date_start.date(),
                        'charge_heures': charge_restante_heures,
                        'employee_ids': [(6, 0, employee_ids)],
                    })
                    continue
                
                # Calculer le total d'heures ouvrées disponibles
                total_heures_ouvrées = sum(
                    (stop - start).total_seconds() / 3600.0
                    for start, stop, _meta in work_intervals
                )
                
                if total_heures_ouvrées <= 0:
                    vals_list.append({
                        'workorder_id': wo.id,
                        'workcenter_id': wo.workcenter_id.id,
                        'workcenter_name': wo.workcenter_id.name,
                        'date': wo.date_start.date(),
                        'charge_heures': charge_restante_heures,
                        'employee_ids': [(6, 0, employee_ids)],
                    })
                    continue
                
                # Répartir proportionnellement sur les jours ouvrés
                heures_par_jour = {}
                for start, stop, _meta in work_intervals:
                    jour = start.date()
                    heures_interval = (stop - start).total_seconds() / 3600.0
                    proportion = heures_interval / total_heures_ouvrées
                    charge_jour = charge_restante_heures * proportion
                    heures_par_jour[jour] = heures_par_jour.get(jour, 0) + charge_jour
                
                for jour, heures in heures_par_jour.items():
                    if heures > 0:
                        vals_list.append({
                            'workorder_id': wo.id,
                            'workcenter_id': wo.workcenter_id.id,
                            'workcenter_name': wo.workcenter_id.name,
                            'date': jour,
                            'charge_heures': heures,
                            'employee_ids': [(6, 0, employee_ids)],
                        })
            
            except Exception as e:
                _logger.error('Erreur workorder %s : %s\n%s', wo.id, e, traceback.format_exc())
                # Fallback
                vals_list.append({
                    'workorder_id': wo.id,
                    'workcenter_id': wo.workcenter_id.id,
                    'workcenter_name': wo.workcenter_id.name,
                    'date': wo.date_start.date(),
                    'charge_heures': charge_restante_heures,
                    'employee_ids': [(6, 0, employee_ids)],
                })
        
        if vals_list:
            self.create(vals_list)
        _logger.info('REFRESH CHARGE TERMINÉ : %d entrées', len(vals_list))


# ─────────────────────────────────────────────────────────────────────────────
# Wizard de refresh (capacité + charge)
# ─────────────────────────────────────────────────────────────────────────────

class CapaciteRefreshWizard(models.TransientModel):
    _name = 'mrp.capacite.refresh.wizard'
    _description = 'Wizard recalcul capacité et charge'

    nb_slots = fields.Integer(string='Slots publiés', readonly=True)
    nb_workorders = fields.Integer(string='Workorders actifs', readonly=True)
    nb_capacite = fields.Integer(string='Entrées capacité', readonly=True)
    nb_charge = fields.Integer(string='Entrées charge', readonly=True)
    message = fields.Char(string='Résultat', readonly=True)

    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        res['nb_slots'] = self.env['planning.slot'].search_count([('state', '=', 'published')])
        res['nb_workorders'] = self.env['mrp.workorder'].search_count([
            ('state', 'not in', ('done', 'cancel')),
            ('date_start', '!=', False)
        ])
        return res

    def action_refresh(self):
        """Recalcule capacité + charge"""
        self.env['mrp.capacite.cache'].refresh()
        self.env['mrp.workorder.charge.cache'].refresh()
        
        nb_capa = self.env['mrp.capacite.cache'].search_count([])
        nb_chrg = self.env['mrp.workorder.charge.cache'].search_count([])
        
        self.write({
            'nb_capacite': nb_capa,
            'nb_charge': nb_chrg,
            'message': f'{nb_capa} capacités + {nb_chrg} charges calculées'
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


# ─────────────────────────────────────────────────────────────────────────────
# Mixin utilitaires SQL
# ─────────────────────────────────────────────────────────────────────────────

class CapaciteMixin(models.AbstractModel):
    _name = 'mrp.capacite.mixin'
    _description = 'Mixin utilitaires capacité'

    def _get_sale_col(self):
        self.env.cr.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'mrp_production'
            AND column_name IN ('sale_id', 'x_sale_id', 'procurement_sale_id', 'x_studio_mtn_mrp_sale_order')
            LIMIT 1
        """)
        row = self.env.cr.fetchone()
        return row[0] if row else None

    def _get_name_expr(self, table, col='name', alias=None):
        ref = alias or table
        self.env.cr.execute("""
            SELECT data_type FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s LIMIT 1
        """, (table, col))
        row = self.env.cr.fetchone()
        dtype = row[0] if row else 'character varying'
        if dtype == 'jsonb':
            return (f"COALESCE({ref}.{col}->>'fr_FR', "
                    f"{ref}.{col}->>'en_US', {ref}.{col}::text)")
        return f"{ref}.{col}::text"

    def _get_projet_fragments(self):
        sale_col = self._get_sale_col()
        pp_name = self._get_name_expr('project_project', alias='pp')
        self.env.cr.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'sale_order' AND column_name = 'x_studio_projet'
        """)
        has_projet = bool(self.env.cr.fetchone())
        return sale_col, pp_name, has_projet


# ─────────────────────────────────────────────────────────────────────────────
# Vue détail workorders
# ─────────────────────────────────────────────────────────────────────────────

class CapaciteChargeDetail(models.Model):
    _name = 'mrp.capacite.charge.detail'
    _inherit = 'mrp.capacite.mixin'
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
    operateurs = fields.Char(string='Opérateur(s)', readonly=True)
    duration_expected = fields.Float(string='Prévu (h)', digits=(10, 2), readonly=True)
    charge_restante = fields.Float(string='Restant (h)', digits=(10, 2), readonly=True)
    state = fields.Char(string='Statut', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, 'mrp_capacite_charge_detail')
        wc_name = self._get_name_expr('mrp_workcenter', alias='wc')
        emp_name = self._get_name_expr('hr_employee', alias='emp')
        sale_col, pp_name, has_projet = self._get_projet_fragments()

        if sale_col:
            sale_join = f"LEFT JOIN sale_order so ON so.id = mp.{sale_col}"
            sale_id_expr = f"mp.{sale_col} AS sale_order_id,"
            sale_name_expr = "so.name AS sale_order_name,"
            projet_join = "LEFT JOIN project_project pp ON pp.id = so.x_studio_projet" if has_projet else ""
            projet_expr = f"{pp_name} AS projet," if has_projet else "NULL::text AS projet,"
        else:
            sale_join = ""
            projet_join = ""
            sale_id_expr = "NULL::integer AS sale_order_id,"
            sale_name_expr = "NULL::text AS sale_order_name,"
            projet_expr = "NULL::text AS projet,"

        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW mrp_capacite_charge_detail AS (
            SELECT
                wcc.id                                      AS id,
                wcc.date,
                wcc.workcenter_id,
                {wc_name}                                   AS workcenter_name,
                wo.production_id,
                mp.name                                     AS production_name,
                {sale_id_expr}
                {sale_name_expr}
                {projet_expr}
                wo.name                                     AS operation_name,
                (
                    SELECT STRING_AGG(DISTINCT {emp_name}, ', ')
                    FROM mrp_workorder_charge_cache_hr_employee_rel rel
                    JOIN hr_employee emp ON emp.id = rel.hr_employee_id
                    WHERE rel.mrp_workorder_charge_cache_id = wcc.id
                )                                           AS operateurs,
                COALESCE(wo.duration_expected, 0) / 60.0   AS duration_expected,
                wcc.charge_heures                           AS charge_restante,
                wo.state
            FROM mrp_workorder_charge_cache wcc
            JOIN mrp_workcenter wc ON wc.id = wcc.workcenter_id
            JOIN mrp_workorder wo ON wo.id = wcc.workorder_id
            JOIN mrp_production mp ON mp.id = wo.production_id
            {sale_join}
            {projet_join}
        )
        """)


# ─────────────────────────────────────────────────────────────────────────────
# Vue capacité vs charge par poste
# ─────────────────────────────────────────────────────────────────────────────

class CapaciteCharge(models.Model):
    _name = 'mrp.capacite.charge'
    _inherit = 'mrp.capacite.mixin'
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
        wc_name = self._get_name_expr('mrp_workcenter', alias='wc')
        sale_col, pp_name, has_projet = self._get_projet_fragments()

        if sale_col and has_projet:
            sale_join = f"LEFT JOIN sale_order so ON so.id = mp.{sale_col}"
            projet_join = "LEFT JOIN project_project pp ON pp.id = so.x_studio_projet"
            projet_agg = f"STRING_AGG(DISTINCT {pp_name}, ', ') AS projets,"
        else:
            sale_join = ""
            projet_join = ""
            projet_agg = "NULL::text AS projets,"

        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW mrp_capacite_charge AS (
            WITH charge AS (
                SELECT
                    wcc.workcenter_id,
                    {wc_name}                                   AS workcenter_name,
                    wcc.date,
                    COUNT(DISTINCT wcc.workorder_id)            AS nb_operations,
                    {projet_agg}
                    SUM(wcc.charge_heures)                      AS charge_heures
                FROM mrp_workorder_charge_cache wcc
                JOIN mrp_workcenter wc ON wc.id = wcc.workcenter_id
                JOIN mrp_workorder wo ON wo.id = wcc.workorder_id
                JOIN mrp_production mp ON mp.id = wo.production_id
                {sale_join}
                {projet_join}
                GROUP BY wcc.workcenter_id, {wc_name}, wcc.date
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


# ─────────────────────────────────────────────────────────────────────────────
# Vue charge par opérateur
# ─────────────────────────────────────────────────────────────────────────────

class CapaciteChargeOperateur(models.Model):
    _name = 'mrp.capacite.charge.operateur'
    _inherit = 'mrp.capacite.mixin'
    _auto = False
    _description = 'Charge par opérateur et par jour'
    _order = 'date asc, employee_name asc'

    date = fields.Date(string='Date', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Opérateur', readonly=True)
    employee_name = fields.Char(string='Opérateur', readonly=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string='Poste', readonly=True)
    workcenter_name = fields.Char(string='Poste', readonly=True)
    nb_operations = fields.Integer(string='Nb opérations', readonly=True)
    charge_heures = fields.Float(string='Charge restante (h)', digits=(10, 2), readonly=True)
    projets = fields.Char(string='Projets', readonly=True)

    def action_voir_detail(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Détail — %s %s' % (self.employee_name, self.date),
            'res_model': 'mrp.capacite.charge.detail',
            'view_mode': 'tree',
            'domain': [
                ('operateurs', 'like', self.employee_name),
                ('date', '=', str(self.date)),
            ],
            'target': 'new',
        }

    def init(self):
        tools.drop_view_if_exists(self.env.cr, 'mrp_capacite_charge_operateur')
        wc_name = self._get_name_expr('mrp_workcenter', alias='wc')
        emp_name = self._get_name_expr('hr_employee', alias='emp')
        sale_col, pp_name, has_projet = self._get_projet_fragments()

        if sale_col and has_projet:
            sale_join = f"LEFT JOIN sale_order so ON so.id = mp.{sale_col}"
            projet_join = "LEFT JOIN project_project pp ON pp.id = so.x_studio_projet"
            projet_agg = f"STRING_AGG(DISTINCT {pp_name}, ', ') AS projets,"
        else:
            sale_join = ""
            projet_join = ""
            projet_agg = "NULL::text AS projets,"

        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW mrp_capacite_charge_operateur AS (
            SELECT
                ROW_NUMBER() OVER (
                    ORDER BY wcc.date, {emp_name}, {wc_name}
                )                                           AS id,
                wcc.date,
                rel.hr_employee_id                          AS employee_id,
                {emp_name}                                  AS employee_name,
                wcc.workcenter_id,
                {wc_name}                                   AS workcenter_name,
                COUNT(DISTINCT wcc.workorder_id)            AS nb_operations,
                {projet_agg}
                SUM(wcc.charge_heures)                      AS charge_heures
            FROM mrp_workorder_charge_cache wcc
            JOIN mrp_workorder_charge_cache_hr_employee_rel rel 
                ON rel.mrp_workorder_charge_cache_id = wcc.id
            JOIN hr_employee emp ON emp.id = rel.hr_employee_id
            JOIN mrp_workcenter wc ON wc.id = wcc.workcenter_id
            JOIN mrp_workorder wo ON wo.id = wcc.workorder_id
            JOIN mrp_production mp ON mp.id = wo.production_id
            {sale_join}
            {projet_join}
            GROUP BY
                wcc.date,
                rel.hr_employee_id,
                {emp_name},
                wcc.workcenter_id,
                {wc_name}
        )
        """)
