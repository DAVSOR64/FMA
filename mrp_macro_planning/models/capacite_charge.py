# -*- coding: utf-8 -*-
from odoo import models, fields, tools, api
import logging
import traceback
import pytz
from datetime import timedelta, datetime

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
    nb_personnes = fields.Integer(string='Nb personnes', default=1)

    def _to_utc(self, dt):
        if dt is None:
            return dt
        if dt.tzinfo is None:
            return pytz.utc.localize(dt)
        return dt.astimezone(pytz.utc)

    def refresh(self):
        """
        Recalcule la capacité depuis mrp.capacity.week (module mrp_capacity_planning).

        Logique :
        - Une ligne mrp.capacity.week = 1 ressource × 1 semaine × 1 poste
        - On ventile la capacité nette hebdomadaire sur les jours ouvrés
          du calendrier de l'affectation (même logique que le calcul standard)
        - capacity_net tient déjà compte des absences, fériés et overrides
        """
        self.search([]).unlink()

        # Vérifie que le module mrp_capacity_planning est installé
        if 'mrp.capacity.week' not in self.env:
            _logger.warning('[MacroPlanning] mrp.capacity.week non disponible — capacité vide')
            return

        # Toutes les semaines avec une capacité nette > 0
        weeks = self.env['mrp.capacity.week'].search([
            ('capacity_net', '>', 0),
        ])

        _logger.info('[MacroPlanning] REFRESH CAPACITE : %d semaines trouvées', len(weeks))

        if not weeks:
            return

        vals_list = []

        for week in weeks:
            if not week.workcenter_id or not week.week_date:
                continue

            calendar = week.resource_calendar_id
            capacity_net = week.capacity_net  # heures nettes de la semaine

            # Jours ouvrés de la semaine selon le calendrier
            jours_ouvres = self._get_working_days(calendar, week.week_date)

            if not jours_ouvres:
                # Fallback : 5 jours si pas de calendrier
                from datetime import timedelta
                jours_ouvres = {
                    week.week_date + timedelta(days=i): 1.0
                    for i in range(5)
                }

            # Heures totales calendrier de la semaine (pour pondération)
            total_cal_hours = sum(jours_ouvres.values())
            if total_cal_hours <= 0:
                continue

            for jour, heures_jour_cal in jours_ouvres.items():
                # Proportion de la capacité nette pour ce jour
                ratio = heures_jour_cal / total_cal_hours
                capacite_jour = round(capacity_net * ratio, 2)

                if capacite_jour <= 0:
                    continue

                vals_list.append({
                    'workcenter_id': week.workcenter_id.id,
                    'workcenter_name': week.workcenter_id.name,
                    'date': jour,
                    'capacite_heures': capacite_jour,
                    'nb_personnes': 1,  # 1 ressource par ligne capacity.week
                })

        # Agrège les lignes du même poste/jour (plusieurs ressources sur même poste)
        aggregated = {}
        for v in vals_list:
            key = (v['workcenter_id'], v['date'])
            if key not in aggregated:
                aggregated[key] = {
                    'workcenter_id': v['workcenter_id'],
                    'workcenter_name': v['workcenter_name'],
                    'date': v['date'],
                    'capacite_heures': 0.0,
                    'nb_personnes': 0,
                }
            aggregated[key]['capacite_heures'] += v['capacite_heures']
            aggregated[key]['nb_personnes'] += 1

        if aggregated:
            self.create(list(aggregated.values()))

        _logger.info(
            '[MacroPlanning] REFRESH CAPACITE TERMINÉ : %d entrées poste/jour créées',
            len(aggregated)
        )

    def _get_working_days(self, calendar, week_date):
        """
        Retourne un dict {date: heures} pour chaque jour ouvré de la semaine.
        Basé sur les attendance_ids du calendrier.
        """
        from datetime import timedelta
        if not calendar or not calendar.attendance_ids:
            return {}

        result = {}
        for att in calendar.attendance_ids:
            day_num = int(att.dayofweek)  # 0=lundi, 6=dimanche
            day_date = week_date + timedelta(days=day_num)
            # S'assure qu'on reste dans la semaine (lundi → dimanche)
            if day_date > week_date + timedelta(days=6):
                continue
            heures = att.hour_to - att.hour_from
            result[day_date] = result.get(day_date, 0) + heures

        return result


# ─────────────────────────────────────────────────────────────────────────────
# Cache CHARGE (depuis Workorders) - VERSION FINALE
# Stocke la charge PRÉVUE par OF/poste/date
# ─────────────────────────────────────────────────────────────────────────────

class WorkorderChargeCache(models.Model):
    _name = 'mrp.workorder.charge.cache'
    _description = 'Cache charge workorder répartie par jour'
    _auto = True
    _order = 'date asc, workcenter_id asc, workorder_id asc'

    workorder_id = fields.Many2one('mrp.workorder', string='Ordre de travail', index=True, ondelete='cascade')
    production_id = fields.Many2one('mrp.production', string='OF', related='workorder_id.production_id', store=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string='Poste', index=True, ondelete='cascade')
    workcenter_name = fields.Char(string='Nom poste')
    date = fields.Date(string='Date', index=True)
    charge_prevue_heures = fields.Float(string='Charge prévue (h)', digits=(10, 2), 
                                         help='Charge planifiée pour ce jour sur cet OF')
    employee_ids = fields.Many2many('hr.employee', string='Opérateurs')

    def _to_utc(self, dt):
        if dt is None:
            return dt
        if dt.tzinfo is None:
            return pytz.utc.localize(dt)
        return dt.astimezone(pytz.utc)

    def refresh(self):
        """Recalcule la charge depuis les workorders actifs - RÉPARTITION JOUR PAR JOUR"""
        self.search([]).unlink()
        
        workorders = self.env['mrp.workorder'].search([
            ('state', 'not in', ('done', 'cancel')),
            ('date_start', '!=', False)
        ])
        
        _logger.info('REFRESH CHARGE : %d workorders actifs', len(workorders))
        if not workorders:
            return
        
        vals_list = []
        batch_size = 50
        count = 0
        
        for wo in workorders:
            count += 1
            
            if not wo.workcenter_id or not wo.date_start:
                continue
            
            # Charge restante TOTALE en heures
            if wo.state in ('pending', 'ready', 'waiting'):
                charge_restante_totale = (wo.duration_expected or 0) / 60.0
            else:
                charge_restante_totale = max((wo.duration_expected or 0) - (wo.duration or 0), 0) / 60.0
            
            if charge_restante_totale <= 0:
                continue
            
            # Récupérer les opérateurs assignés
            employee_ids = self.env['mrp.workcenter.productivity'].search([
                ('workorder_id', '=', wo.id),
                ('employee_id', '!=', False)
            ]).mapped('employee_id').ids
            
            # Calendrier du workcenter
            calendar = wo.workcenter_id.resource_calendar_id
            
            # Date de début de l'opération (macro_date_planned ou date_start)
            date_start_operation = wo.macro_date_planned if hasattr(wo, 'macro_date_planned') and wo.macro_date_planned else wo.date_start
            
            if not date_start_operation:
                continue
            
            # OPTIMISATION : Si pas de calendrier OU durée > 80h → tout sur date_start
            if not calendar or charge_restante_totale > 80:
                vals_list.append({
                    'workorder_id': wo.id,
                    'workcenter_id': wo.workcenter_id.id,
                    'workcenter_name': wo.workcenter_id.name,
                    'date': date_start_operation.date(),
                    'charge_prevue_heures': charge_restante_totale,
                    'employee_ids': [(6, 0, employee_ids)],
                })
                continue
            
            # Calculer une fenêtre large pour récupérer les jours ouvrés (60 jours)
            date_end_window = date_start_operation + timedelta(days=60)
            
            try:
                date_start_utc = self._to_utc(date_start_operation)
                date_end_utc = self._to_utc(date_end_window)
                
                # Récupérer les intervalles de travail
                intervals = calendar._work_intervals_batch(date_start_utc, date_end_utc)
                work_intervals = intervals.get(False, [])
                
                if not work_intervals:
                    vals_list.append({
                        'workorder_id': wo.id,
                        'workcenter_id': wo.workcenter_id.id,
                        'workcenter_name': wo.workcenter_id.name,
                        'date': date_start_operation.date(),
                        'charge_prevue_heures': charge_restante_totale,
                        'employee_ids': [(6, 0, employee_ids)],
                    })
                    continue
                
                # Calculer les heures ouvrées par jour
                heures_calendrier_par_jour = {}
                for start, stop, _meta in work_intervals:
                    jour = start.date()
                    heures_interval = (stop - start).total_seconds() / 3600.0
                    heures_calendrier_par_jour[jour] = heures_calendrier_par_jour.get(jour, 0) + heures_interval
                
                if not heures_calendrier_par_jour:
                    vals_list.append({
                        'workorder_id': wo.id,
                        'workcenter_id': wo.workcenter_id.id,
                        'workcenter_name': wo.workcenter_id.name,
                        'date': date_start_operation.date(),
                        'charge_prevue_heures': charge_restante_totale,
                        'employee_ids': [(6, 0, employee_ids)],
                    })
                    continue
                
                # RÉPARTITION JOUR PAR JOUR avec plafonnement à la capacité calendrier
                charge_restante = charge_restante_totale
                jours_tries = sorted(heures_calendrier_par_jour.keys())
                
                for jour in jours_tries:
                    if charge_restante <= 0:
                        break
                    
                    capacite_jour = heures_calendrier_par_jour[jour]
                    charge_ce_jour = min(charge_restante, capacite_jour)
                    
                    if charge_ce_jour > 0:
                        vals_list.append({
                            'workorder_id': wo.id,
                            'workcenter_id': wo.workcenter_id.id,
                            'workcenter_name': wo.workcenter_id.name,
                            'date': jour,
                            'charge_prevue_heures': charge_ce_jour,
                            'employee_ids': [(6, 0, employee_ids)],
                        })
                        charge_restante -= charge_ce_jour
                
                # S'il reste de la charge après 60 jours
                if charge_restante > 0:
                    dernier_jour = jours_tries[-1] if jours_tries else date_start_operation.date()
                    vals_list.append({
                        'workorder_id': wo.id,
                        'workcenter_id': wo.workcenter_id.id,
                        'workcenter_name': wo.workcenter_id.name,
                        'date': dernier_jour,
                        'charge_prevue_heures': charge_restante,
                        'employee_ids': [(6, 0, employee_ids)],
                    })
                    _logger.warning('WO %s : charge restante %sh après 60 jours', wo.id, charge_restante)
            
            except Exception as e:
                _logger.error('Erreur workorder %s : %s', wo.id, str(e))
                vals_list.append({
                    'workorder_id': wo.id,
                    'workcenter_id': wo.workcenter_id.id,
                    'workcenter_name': wo.workcenter_id.name,
                    'date': date_start_operation.date(),
                    'charge_prevue_heures': charge_restante_totale,
                    'employee_ids': [(6, 0, employee_ids)],
                })
            
            # OPTIMISATION : Commit par batch
            if count % batch_size == 0 and vals_list:
                self.create(vals_list)
                self.env.cr.commit()
                _logger.info('REFRESH CHARGE : %d/%d traités', count, len(workorders))
                vals_list = []
        
        # Dernier batch
        if vals_list:
            self.create(vals_list)
        
        _logger.info('REFRESH CHARGE TERMINÉ : %d workorders traités', count)


# ─────────────────────────────────────────────────────────────────────────────
# Wizard de refresh
# ─────────────────────────────────────────────────────────────────────────────

class CapaciteRefreshWizard(models.TransientModel):
    _name = 'mrp.capacite.refresh.wizard'
    _description = 'Wizard recalcul capacité et charge'

    nb_slots = fields.Integer(string='Semaines capacité (mrp_capacity_planning)', readonly=True)
    nb_workorders = fields.Integer(string='Workorders actifs', readonly=True)
    nb_capacite = fields.Integer(string='Entrées capacité', readonly=True)
    nb_charge = fields.Integer(string='Entrées charge', readonly=True)
    message = fields.Char(string='Résultat', readonly=True)

    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'mrp.capacity.week' in self.env:
            res['nb_slots'] = self.env['mrp.capacity.week'].search_count([
                ('capacity_net', '>', 0),
            ])
        else:
            res['nb_slots'] = 0
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
# Vue détail workorders - AVEC CUMULS
# ─────────────────────────────────────────────────────────────────────────────

class CapaciteChargeDetail(models.Model):
    _name = 'mrp.capacite.charge.detail'
    _inherit = 'mrp.capacite.mixin'
    _auto = False
    _description = 'Détail opérations par poste/jour avec cumuls'
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
    prevu_jour = fields.Float(string='Prévu ce jour (h)', digits=(10, 2), readonly=True)
    effectue_jour = fields.Float(string='Effectué ce jour (h)', digits=(10, 2), readonly=True)
    cumul_prevu = fields.Float(string='Cumul prévu (h)', digits=(10, 2), readonly=True)
    cumul_effectue = fields.Float(string='Cumul effectué (h)', digits=(10, 2), readonly=True)
    ecart = fields.Float(string='Écart (h)', digits=(10, 2), readonly=True)
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
            WITH effectue_par_jour AS (
                SELECT 
                    wop.workorder_id,
                    DATE(wop.date_start) AS date,
                    SUM(COALESCE(wop.duration, 0)) / 60.0 AS effectue_heures
                FROM mrp_workcenter_productivity wop
                WHERE wop.date_start IS NOT NULL
                GROUP BY wop.workorder_id, DATE(wop.date_start)
            ),
            cumuls AS (
                SELECT
                    wcc.id,
                    wcc.workorder_id,
                    wcc.date,
                    wcc.charge_prevue_heures,
                    COALESCE(epj.effectue_heures, 0) AS effectue_jour,
                    SUM(wcc.charge_prevue_heures) OVER (
                        PARTITION BY wcc.workorder_id 
                        ORDER BY wcc.date 
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                    ) AS cumul_prevu,
                    SUM(COALESCE(epj.effectue_heures, 0)) OVER (
                        PARTITION BY wcc.workorder_id 
                        ORDER BY wcc.date 
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                    ) AS cumul_effectue
                FROM mrp_workorder_charge_cache wcc
                LEFT JOIN effectue_par_jour epj 
                    ON epj.workorder_id = wcc.workorder_id 
                    AND epj.date = wcc.date
            )
            SELECT
                cum.id                                      AS id,
                cum.date,
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
                    FROM mrp_workcenter_productivity wop
                    JOIN hr_employee emp ON emp.id = wop.employee_id
                    WHERE wop.workorder_id = wo.id
                      AND wop.employee_id IS NOT NULL
                )                                           AS operateurs,
                cum.charge_prevue_heures                    AS prevu_jour,
                cum.effectue_jour                           AS effectue_jour,
                cum.cumul_prevu                             AS cumul_prevu,
                cum.cumul_effectue                          AS cumul_effectue,
                cum.cumul_effectue - cum.cumul_prevu        AS ecart,
                wo.state
            FROM cumuls cum
            JOIN mrp_workorder_charge_cache wcc ON wcc.id = cum.id
            JOIN mrp_workcenter wc ON wc.id = wcc.workcenter_id
            JOIN mrp_workorder wo ON wo.id = wcc.workorder_id
            JOIN mrp_production mp ON mp.id = wo.production_id
            {sale_join}
            {projet_join}
        )
        """)


# ─────────────────────────────────────────────────────────────────────────────
# Vue capacité vs charge par poste - AVEC CUMULS
# ─────────────────────────────────────────────────────────────────────────────

class CapaciteCharge(models.Model):
    _name = 'mrp.capacite.charge'
    _inherit = 'mrp.capacite.mixin'
    _auto = False
    _description = 'Capacité vs Charge par poste avec cumuls'
    _order = 'date asc, workcenter_id asc'

    date = fields.Date(string='Date', readonly=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string='Poste de travail', readonly=True)
    workcenter_name = fields.Char(string='Poste', readonly=True)
    nb_personnes = fields.Integer(string='Personnes', readonly=True)
    capacite_heures = fields.Float(string='Capacité (h)', digits=(10, 2), readonly=True)
    nb_operations = fields.Integer(string='Nb opérations', readonly=True)
    
    charge_prevue_jour = fields.Float(string='Charge prévue ce jour (h)', digits=(10, 2), readonly=True)
    charge_effectuee_jour = fields.Float(string='Charge effectuée ce jour (h)', digits=(10, 2), readonly=True)
    cumul_prevu = fields.Float(string='Cumul prévu (h)', digits=(10, 2), readonly=True)
    cumul_effectue = fields.Float(string='Cumul effectué (h)', digits=(10, 2), readonly=True)
    ecart = fields.Float(string='Écart (h)', digits=(10, 2), readonly=True, 
                         help='Cumul effectué - Cumul prévu (négatif = retard, positif = avance)')
    
    taux_charge = fields.Float(string='Taux charge (%)', digits=(10, 1), readonly=True)
    solde_heures = fields.Float(string='Solde (h)', digits=(10, 2), readonly=True)

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

        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW mrp_capacite_charge AS (
            WITH effectue_par_jour AS (
                SELECT 
                    wo.workcenter_id,
                    DATE(wop.date_start) AS date,
                    SUM(COALESCE(wop.duration, 0)) / 60.0 AS effectue_heures
                FROM mrp_workcenter_productivity wop
                JOIN mrp_workorder wo ON wo.id = wop.workorder_id
                WHERE wop.date_start IS NOT NULL
                GROUP BY wo.workcenter_id, DATE(wop.date_start)
            ),
            charge AS (
                SELECT
                    wcc.workcenter_id,
                    wcc.date,
                    COUNT(DISTINCT wcc.workorder_id)                AS nb_operations,
                    SUM(wcc.charge_prevue_heures)                   AS charge_prevue_jour,
                    COALESCE(epj.effectue_heures, 0)                AS charge_effectuee_jour
                FROM mrp_workorder_charge_cache wcc
                LEFT JOIN effectue_par_jour epj 
                    ON epj.workcenter_id = wcc.workcenter_id 
                    AND epj.date = wcc.date
                GROUP BY wcc.workcenter_id, wcc.date, epj.effectue_heures
            ),
            capacite AS (
                SELECT 
                    workcenter_id, 
                    date,
                    SUM(capacite_heures) AS capacite_heures,
                    MAX(nb_personnes) AS nb_personnes
                FROM mrp_capacite_cache
                GROUP BY workcenter_id, date
            ),
            all_keys AS (
                SELECT workcenter_id, date FROM charge
                UNION
                SELECT workcenter_id, date FROM capacite
            ),
            with_cumuls AS (
                SELECT
                    ak.workcenter_id,
                    ak.date,
                    COALESCE(cap.capacite_heures, 0)            AS capacite_heures,
                    COALESCE(cap.nb_personnes, 0)               AS nb_personnes,
                    COALESCE(ch.nb_operations, 0)               AS nb_operations,
                    COALESCE(ch.charge_prevue_jour, 0)          AS charge_prevue_jour,
                    COALESCE(ch.charge_effectuee_jour, 0)       AS charge_effectuee_jour,
                    SUM(COALESCE(ch.charge_prevue_jour, 0)) OVER (
                        PARTITION BY ak.workcenter_id 
                        ORDER BY ak.date 
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                    ) AS cumul_prevu,
                    SUM(COALESCE(ch.charge_effectuee_jour, 0)) OVER (
                        PARTITION BY ak.workcenter_id 
                        ORDER BY ak.date 
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                    ) AS cumul_effectue
                FROM all_keys ak
                LEFT JOIN charge   ch  ON ch.workcenter_id  = ak.workcenter_id AND ch.date = ak.date
                LEFT JOIN capacite cap ON cap.workcenter_id = ak.workcenter_id AND cap.date = ak.date
            )
            SELECT
                ROW_NUMBER() OVER (ORDER BY date, workcenter_id) AS id,
                workcenter_id,
                (SELECT {wc_name} FROM mrp_workcenter wc WHERE wc.id = workcenter_id) AS workcenter_name,
                date,
                nb_personnes,
                capacite_heures,
                nb_operations,
                charge_prevue_jour,
                charge_effectuee_jour,
                cumul_prevu,
                cumul_effectue,
                cumul_effectue - cumul_prevu AS ecart,
                charge_prevue_jour - capacite_heures AS solde_heures,
                CASE
                    WHEN capacite_heures > 0
                        THEN ROUND(((charge_prevue_jour / capacite_heures) * 100.0)::numeric, 1)
                    WHEN charge_prevue_jour > 0 THEN 999
                    ELSE 0
                END AS taux_charge
            FROM with_cumuls
        )
        """)


# ─────────────────────────────────────────────────────────────────────────────
# Vue charge par opérateur (inchangée)
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
                wop.employee_id                             AS employee_id,
                {emp_name}                                  AS employee_name,
                wcc.workcenter_id,
                {wc_name}                                   AS workcenter_name,
                COUNT(DISTINCT wcc.workorder_id)            AS nb_operations,
                {projet_agg}
                SUM(wcc.charge_prevue_heures)               AS charge_heures
            FROM mrp_workorder_charge_cache wcc
            JOIN mrp_workorder wo ON wo.id = wcc.workorder_id
            JOIN mrp_workcenter_productivity wop ON wop.workorder_id = wo.id
            JOIN hr_employee emp ON emp.id = wop.employee_id
            JOIN mrp_workcenter wc ON wc.id = wcc.workcenter_id
            JOIN mrp_production mp ON mp.id = wo.production_id
            {sale_join}
            {projet_join}
            WHERE wop.employee_id IS NOT NULL
            GROUP BY
                wcc.date,
                wop.employee_id,
                {emp_name},
                wcc.workcenter_id,
                {wc_name}
        )
        """)
