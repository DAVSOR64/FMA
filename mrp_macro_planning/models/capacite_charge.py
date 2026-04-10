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
        Recalcule la capacité par poste/jour.

        Source 1 (prioritaire) : mrp.capacity.week — capacité nette avec congés/absences
        Source 2 (fallback)    : calendrier du workcenter × nb_resources configurées,
                                 pour les dates de charge qui n'ont pas de semaine capacité.

        On couvre TOUTES les dates présentes dans mrp_workorder_charge_cache,
        afin que le tableau ne montre jamais 0 capacité faute de données.
        """
        self.search([]).unlink()

        aggregated = {}

        # ── Source 1 : mrp.capacity.week ──────────────────────────────────────
        if 'mrp.capacity.week' in self.env:
            weeks = self.env['mrp.capacity.week'].search([])
            _logger.info('[MacroPlanning] REFRESH CAPACITE : %d semaines mrp.capacity.week', len(weeks))

            for week in weeks:
                if not week.workcenter_id or not week.week_date:
                    continue

                daily_hours = self._get_daily_capacity_map(week)
                if not daily_hours:
                    continue

                for jour, capacite_jour in daily_hours.items():
                    key = (week.workcenter_id.id, jour)
                    if key not in aggregated:
                        aggregated[key] = {
                            'workcenter_id': week.workcenter_id.id,
                            'workcenter_name': week.workcenter_id.name,
                            'date': jour,
                            'capacite_heures': 0.0,
                            'nb_personnes': 0,
                        }
                    aggregated[key]['capacite_heures'] += round(capacite_jour, 2)
                    aggregated[key]['nb_personnes'] += 1
        else:
            _logger.warning('[MacroPlanning] mrp.capacity.week non disponible — fallback calendrier uniquement')

        # ── Source 2 : fallback calendrier pour les dates sans capacité ────────
        # Récupérer toutes les dates/postes présents dans le cache charge
        self.env.cr.execute("""
            SELECT DISTINCT workcenter_id, date
            FROM mrp_workorder_charge_cache
            ORDER BY workcenter_id, date
        """)
        charge_keys = self.env.cr.fetchall()

        if charge_keys:
            # Dates manquantes = dates de charge sans entrée capacité
            missing_keys = [(wc_id, d) for wc_id, d in charge_keys if (wc_id, d) not in aggregated]
            _logger.info('[MacroPlanning] %d clés charge sans capacité → fallback calendrier', len(missing_keys))

            # Grouper par workcenter pour éviter de recalculer le calendrier N fois
            from collections import defaultdict
            missing_by_wc = defaultdict(set)
            for wc_id, d in missing_keys:
                missing_by_wc[wc_id].add(d)

            for wc_id, dates in missing_by_wc.items():
                wc = self.env['mrp.workcenter'].browse(wc_id)
                if not wc.exists():
                    continue

                calendar = wc.resource_calendar_id
                if not calendar:
                    # Pas de calendrier : on met 0 pour que la ligne existe
                    for d in dates:
                        key = (wc_id, d)
                        if key not in aggregated:
                            aggregated[key] = {
                                'workcenter_id': wc_id,
                                'workcenter_name': wc.name,
                                'date': d,
                                'capacite_heures': 0.0,
                                'nb_personnes': 0,
                            }
                    continue

                # Nombre de ressources configurées sur ce workcenter
                # (capacity = nb_resources × heures_calendrier_jour)
                nb_resources = max(1, wc.capacity or 1)

                # Calculer les heures par jour sur la plage nécessaire
                min_date = min(dates)
                max_date = max(dates)
                start_dt = self._to_utc(datetime.combine(min_date, datetime.min.time()))
                end_dt = self._to_utc(datetime.combine(max_date + timedelta(days=1), datetime.min.time()))

                try:
                    intervals = calendar._work_intervals_batch(start_dt, end_dt)
                    work_intervals = intervals.get(False, [])

                    heures_par_jour = {}
                    for start, stop, _meta in work_intervals:
                        jour = start.date()
                        heures_par_jour[jour] = heures_par_jour.get(jour, 0) + (stop - start).total_seconds() / 3600.0

                    for d in dates:
                        key = (wc_id, d)
                        if key not in aggregated:
                            h = round(heures_par_jour.get(d, 0.0) * nb_resources, 2)
                            aggregated[key] = {
                                'workcenter_id': wc_id,
                                'workcenter_name': wc.name,
                                'date': d,
                                'capacite_heures': h,
                                'nb_personnes': nb_resources,
                            }
                except Exception as e:
                    _logger.error('[MacroPlanning] Fallback calendrier workcenter %s : %s', wc_id, e)
                    for d in dates:
                        key = (wc_id, d)
                        if key not in aggregated:
                            aggregated[key] = {
                                'workcenter_id': wc_id,
                                'workcenter_name': wc.name,
                                'date': d,
                                'capacite_heures': 0.0,
                                'nb_personnes': 0,
                            }

        if aggregated:
            self.create(list(aggregated.values()))

        _logger.info(
            '[MacroPlanning] REFRESH CAPACITE TERMINÉ : %d entrées poste/jour créées',
            len(aggregated)
        )

    def _get_daily_capacity_map(self, week):
        """
        Retourne {date: heures_nettes} pour une semaine de capacité.

        Logique : on utilise directement capacity_net (déjà calculé dans mrp.capacity.week,
        tenant compte du taux d'affectation, des congés, absences, fériés) et on le
        répartit proportionnellement sur les jours ouvrés de la semaine selon le calendrier.

        Ex : GUILLON 50% → capacity_net=22,50h sur 5 jours ouvrés → 4,50h/jour
             DESORMEAUX 100% → capacity_net=38,50h sur 5 jours ouvrés → 7,70h/jour
        """
        calendar = week.override_calendar_id or week.resource_calendar_id
        if not calendar:
            return {}

        # capacity_net est LA valeur de référence — déjà nette de tout
        capacity_net = week.capacity_net or 0.0
        if capacity_net <= 0:
            return {}

        week_start = week.week_date
        week_end = week.week_end_date or (week.week_date + timedelta(days=6))

        # Récupérer les jours ouvrés de la semaine et leurs heures brutes
        # (pour calculer la proportion de chaque jour)
        base_map = self._get_working_days(calendar, week_start)
        if not base_map:
            return {}

        # Filtrer uniquement les jours dans la fenêtre semaine
        jours_ouvres = {d: h for d, h in base_map.items() if week_start <= d <= week_end}
        if not jours_ouvres:
            return {}

        total_heures_brutes = sum(jours_ouvres.values())
        if total_heures_brutes <= 0:
            return {}

        # Répartir capacity_net proportionnellement aux heures de chaque jour
        # (gère les demi-journées, jours fériés qui réduisent la capacité brute d'un jour)
        result = {}
        total_attribue = 0.0
        jours_tries = sorted(jours_ouvres.keys())

        for i, jour in enumerate(jours_tries):
            if i < len(jours_tries) - 1:
                h_jour = round(capacity_net * jours_ouvres[jour] / total_heures_brutes, 2)
            else:
                # Dernier jour : prendre le reste pour éviter les erreurs d'arrondi
                h_jour = round(capacity_net - total_attribue, 2)
            result[jour] = max(0.0, h_jour)
            total_attribue += h_jour

        return result

    def _get_working_days(self, calendar, week_date):
        """Capacité réelle par jour via _work_intervals_batch (fiable, sans pauses)."""
        if not calendar:
            return {}

        result = {}

        # Fenêtre semaine
        start_dt = datetime.combine(week_date, datetime.min.time())
        end_dt = start_dt + timedelta(days=7)

        try:
            start_dt = self._to_utc(start_dt)
            end_dt = self._to_utc(end_dt)

            intervals = calendar._work_intervals_batch(start_dt, end_dt)
            work_intervals = intervals.get(False, [])

            for start, stop, _meta in work_intervals:
                day = start.date()
                hours = (stop - start).total_seconds() / 3600.0

                result[day] = result.get(day, 0.0) + hours

        except Exception as e:
            _logger.error("Erreur calcul calendrier : %s", str(e))
            return {}

        # arrondi final
        return {d: round(h, 2) for d, h in result.items()}

    def _get_calendar_leave_hours_by_day(self, calendar, week_start, week_end):
        res = {}
        if not calendar:
            return res

        leaves = self.env['resource.calendar.leaves'].search([
            ('calendar_id', '=', calendar.id),
            ('date_from', '<=', fields.Datetime.to_string(datetime.combine(week_end, datetime.max.time()))),
            ('date_to', '>=', fields.Datetime.to_string(datetime.combine(week_start, datetime.min.time()))),
        ])
        for leave in leaves:
            self._accumulate_overlap_by_day(res, calendar, leave.date_from, leave.date_to, week_start, week_end)
        return res

    def _get_employee_leave_hours_by_day(self, employee, calendar, week_start, week_end):
        res = {}
        if not employee:
            return res

        leaves = self.env['hr.leave'].search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'validate'),
            ('date_from', '<=', fields.Datetime.to_string(datetime.combine(week_end, datetime.max.time()))),
            ('date_to', '>=', fields.Datetime.to_string(datetime.combine(week_start, datetime.min.time()))),
        ])
        for leave in leaves:
            self._accumulate_overlap_by_day(res, calendar, leave.date_from, leave.date_to, week_start, week_end)
        return res

    def _accumulate_overlap_by_day(self, bucket, calendar, leave_start, leave_end, week_start, week_end):
        """Ajoute dans bucket les heures d'absence recouvrant le calendrier, par jour."""
        if not leave_start or not leave_end or not calendar:
            return

        cal_tz_name = calendar.tz or 'UTC'
        try:
            tz = pytz.timezone(cal_tz_name)
        except Exception:
            tz = pytz.UTC

        # normalise en UTC aware
        if leave_start.tzinfo is None:
            leave_start = pytz.UTC.localize(leave_start)
        else:
            leave_start = leave_start.astimezone(pytz.UTC)
        if leave_end.tzinfo is None:
            leave_end = pytz.UTC.localize(leave_end)
        else:
            leave_end = leave_end.astimezone(pytz.UTC)

        for i in range(7):
            day = week_start + timedelta(days=i)
            if day > week_end:
                break

            weekday = str(day.weekday())
            attendances = calendar.attendance_ids.filtered(lambda a: a.dayofweek == weekday and a.display_type != 'line_section')
            if not attendances:
                continue

            hours = 0.0
            for att in attendances:
                local_start = tz.localize(datetime.combine(day, datetime.min.time()) + timedelta(hours=att.hour_from))
                local_end = tz.localize(datetime.combine(day, datetime.min.time()) + timedelta(hours=att.hour_to))
                att_start = local_start.astimezone(pytz.UTC)
                att_end = local_end.astimezone(pytz.UTC)

                overlap_start = max(att_start, leave_start)
                overlap_end = min(att_end, leave_end)
                if overlap_end > overlap_start:
                    hours += (overlap_end - overlap_start).total_seconds() / 3600.0

            if hours > 0:
                bucket[day] = round(bucket.get(day, 0.0) + hours, 2)


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

    def _get_wo_date_start(self, wo):
        """
        Retourne la meilleure date de début disponible sur le workorder.
        Priorité : macro_planned_start > date_planned_start > date_start
        Odoo 17 : le champ planifié est 'date_planned_start' (pas 'date_start' pour les WOs non démarrés).
        """
        for fname in ('macro_planned_start', 'date_planned_start', 'date_start'):
            val = getattr(wo, fname, False)
            if val:
                return val
        return False

    def refresh(self):
        """Recalcule la charge depuis les workorders actifs - RÉPARTITION JOUR PAR JOUR"""
        self.search([]).unlink()

        # Odoo 17 : les WOs planifiés ont date_planned_start, pas forcément date_start
        # On prend tous les WOs actifs (pas done/cancel) avec au moins une date planifiée
        workorders = self.env['mrp.workorder'].search([
            ('state', 'not in', ('done', 'cancel')),
            ('production_id.state', 'not in', ('done', 'cancel')),
        ])

        # Filtrer côté Python pour couvrir tous les champs de date possibles
        workorders = workorders.filtered(lambda w: self._get_wo_date_start(w))

        _logger.info('REFRESH CHARGE : %d workorders actifs avec date planifiée', len(workorders))
        if not workorders:
            return
        
        vals_list = []
        batch_size = 50
        count = 0
        
        for wo in workorders:
            count += 1
            
            if not wo.workcenter_id:
                continue
            
            # Charge restante TOTALE en heures, divisée par le nombre de ressources
            nb_resources = max(1, getattr(wo, 'x_nb_resources', 1) or 1)
            if wo.state in ('pending', 'ready', 'waiting'):
                charge_restante_totale = (wo.duration_expected or 0) / 60.0 / nb_resources
            else:
                # En cours : charge restante = prévu - réalisé
                charge_restante_totale = max(
                    (wo.duration_expected or 0) - (wo.duration or 0), 0
                ) / 60.0 / nb_resources
            
            if charge_restante_totale <= 0:
                _logger.debug('WO %s : charge nulle, ignoré', wo.id)
                continue
            
            # Récupérer les opérateurs assignés
            employee_ids = self.env['mrp.workcenter.productivity'].search([
                ('workorder_id', '=', wo.id),
                ('employee_id', '!=', False)
            ]).mapped('employee_id').ids
            
            # Calendrier du workcenter
            calendar = wo.workcenter_id.resource_calendar_id
            
            # Date de début de l'opération
            date_start_operation = self._get_wo_date_start(wo)
            _logger.debug('WO %s (%s) : date_start=%s charge=%.2fh', 
                         wo.id, wo.name, date_start_operation, charge_restante_totale)
            
            if not date_start_operation:
                continue

            # DATE DE DÉBUT : on ne tient PAS compte de l'heure, seulement du jour ouvré
            date_debut = date_start_operation.date() if hasattr(date_start_operation, 'date') else date_start_operation

            # Si pas de calendrier → tout sur le jour de début
            if not calendar:
                vals_list.append({
                    'workorder_id': wo.id,
                    'workcenter_id': wo.workcenter_id.id,
                    'workcenter_name': wo.workcenter_id.name,
                    'date': date_debut,
                    'charge_prevue_heures': charge_restante_totale,
                    'employee_ids': [(6, 0, employee_ids)],
                })
                continue

            # Fenêtre large : depuis le début du premier jour ouvré (minuit) sur 90 jours
            date_end_window = datetime.combine(date_debut, datetime.min.time()) + timedelta(days=90)

            try:
                # On part du début de la journée (minuit) pour avoir la journée complète
                date_start_utc = self._to_utc(datetime.combine(date_debut, datetime.min.time()))
                date_end_utc = self._to_utc(date_end_window)

                # Récupérer les intervalles de travail (journées complètes)
                intervals = calendar._work_intervals_batch(date_start_utc, date_end_utc)
                work_intervals = intervals.get(False, [])

                if not work_intervals:
                    vals_list.append({
                        'workorder_id': wo.id,
                        'workcenter_id': wo.workcenter_id.id,
                        'workcenter_name': wo.workcenter_id.name,
                        'date': date_debut,
                        'charge_prevue_heures': charge_restante_totale,
                        'employee_ids': [(6, 0, employee_ids)],
                    })
                    continue

                # Heures ouvrées par jour (journées COMPLÈTES - sans tenir compte de l'heure de début)
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
                        'date': date_debut,
                        'charge_prevue_heures': charge_restante_totale,
                        'employee_ids': [(6, 0, employee_ids)],
                    })
                    continue

                # RÉPARTITION JOUR PAR JOUR — journées complètes, plafonnées à la capa du calendrier
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
                            'charge_prevue_heures': round(charge_ce_jour, 2),
                            'employee_ids': [(6, 0, employee_ids)],
                        })
                        charge_restante -= charge_ce_jour

                # S'il reste de la charge après 90 jours calendaires
                if charge_restante > 0:
                    dernier_jour = jours_tries[-1] if jours_tries else date_debut
                    vals_list.append({
                        'workorder_id': wo.id,
                        'workcenter_id': wo.workcenter_id.id,
                        'workcenter_name': wo.workcenter_id.name,
                        'date': dernier_jour,
                        'charge_prevue_heures': round(charge_restante, 2),
                        'employee_ids': [(6, 0, employee_ids)],
                    })
                    _logger.warning('WO %s : charge restante %.2fh après 90 jours', wo.id, charge_restante)
            
            except Exception as e:
                _logger.error('Erreur workorder %s : %s\n%s', wo.id, str(e), traceback.format_exc())
                vals_list.append({
                    'workorder_id': wo.id,
                    'workcenter_id': wo.workcenter_id.id,
                    'workcenter_name': wo.workcenter_id.name,
                    'date': date_debut,
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
        # Compter tous les WOs actifs avec au moins une date planifiée
        charge_model = self.env['mrp.workorder.charge.cache']
        all_wos = self.env['mrp.workorder'].search([
            ('state', 'not in', ('done', 'cancel')),
            ('production_id.state', 'not in', ('done', 'cancel')),
        ])
        wo_avec_date = all_wos.filtered(lambda w: charge_model._get_wo_date_start(w))
        res['nb_workorders'] = len(wo_avec_date)
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
    nb_resources = fields.Integer(string='Nb ressources', readonly=True)
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
                COALESCE(wo.x_nb_resources, 1)              AS nb_resources,
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
    nb_resources = fields.Integer(string='Nb ressources', readonly=True)
    
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
                    COALESCE(epj.effectue_heures, 0)                AS charge_effectuee_jour,
                    SUM(COALESCE(wo.x_nb_resources, 1))             AS nb_resources
                FROM mrp_workorder_charge_cache wcc
                JOIN mrp_workorder wo ON wo.id = wcc.workorder_id
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
                    COALESCE(ch.nb_resources, 0)                AS nb_resources,
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
                nb_resources,
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
