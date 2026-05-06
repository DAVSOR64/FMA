# -*- coding: utf-8 -*-
import logging
import pytz
from datetime import timedelta, datetime, time

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class MrpCapacityWeek(models.Model):
    _name = 'mrp.capacity.week'
    _description = 'Capacité hebdomadaire'
    _order = 'week_date, capacity_resource_id'
    _rec_name = 'display_name'

    # ── Affectation parente ────────────────────────────────────────────────────
    capacity_resource_id = fields.Many2one(
        'mrp.capacity.resource',
        string='Affectation',
        required=True,
        index=True,
        ondelete='cascade',
    )

    # ── Raccourcis stockés ─────────────────────────────────────────────────────
    employee_id = fields.Many2one(
        related='capacity_resource_id.employee_id',
        store=True, string='Ressource', index=True,
    )
    workcenter_id = fields.Many2one(
        related='capacity_resource_id.workcenter_id',
        store=True, string='Poste de travail', index=True,
    )
    resource_calendar_id = fields.Many2one(
        related='capacity_resource_id.resource_calendar_id',
        store=True, string='Calendrier',
    )
    allocation_rate = fields.Float(
        related='capacity_resource_id.allocation_rate',
        store=True, string='Taux (%)',
    )

    # ── Semaine ────────────────────────────────────────────────────────────────
    week_date = fields.Date(string='Semaine (lundi)', required=True, index=True)
    week_end_date = fields.Date(string='Fin semaine', compute='_compute_week_bounds', store=True)
    week_number = fields.Char(string='N° semaine', compute='_compute_week_bounds', store=True)
    week_label = fields.Char(string='Semaine', compute='_compute_week_bounds', store=True)

    # ── Capacité brute calendrier ──────────────────────────────────────────────
    capacity_standard = fields.Float(
        string='Standard (H)',
        compute='_compute_capacity_standard',
        store=True,
        digits=(6, 2),
    )

    # ── Override : calendrier alternatif pour cette semaine ────────────────────
    override_calendar_id = fields.Many2one(
        'resource.calendar',
        string='Calendrier alternatif',
        help='Choisissez un calendrier différent pour cette semaine uniquement. '
             'Laissez vide pour utiliser le calendrier de l\'affectation.',
    )
    capacity_override = fields.Float(
        string='Surchargé (H)',
        default=0.0,
        digits=(6, 2),
        help='Valeur brute forcée sans passer par un calendrier. '
             'À utiliser uniquement si aucun calendrier ne correspond. '
             'Laissez à 0 pour utiliser le calendrier.',
    )
    is_overridden = fields.Boolean(
        compute='_compute_is_overridden', store=True, string='Override actif',
    )

    # ── Absences automatiques ──────────────────────────────────────────────────
    hours_public_holiday = fields.Float(
        string='Jours fériés (H)', compute='_compute_absences', store=True, digits=(6, 2),
    )
    hours_leaves = fields.Float(
        string='Congés (H)', compute='_compute_absences', store=True, digits=(6, 2),
    )
    hours_sick = fields.Float(
        string='Maladie (H)', compute='_compute_absences', store=True, digits=(6, 2),
    )
    hours_absence_total = fields.Float(
        string='Total absences (H)', compute='_compute_absences', store=True, digits=(6, 2),
    )

    # ── Capacité nette ─────────────────────────────────────────────────────────
    capacity_net = fields.Float(
        string='Capacité nette (H)',
        compute='_compute_capacity_net',
        store=True,
        digits=(6, 2),
    )

    # ── Charge / delta ─────────────────────────────────────────────────────────
    hours_planned = fields.Float(string='Charge (H)', default=0.0, digits=(6, 2))
    delta = fields.Float(
        string='Delta (H)', compute='_compute_delta', store=True, digits=(6, 2),
    )

    # ── Affichage ──────────────────────────────────────────────────────────────
    display_name = fields.Char(compute='_compute_display_name', store=True)
    color = fields.Integer(compute='_compute_color')
    note = fields.Char(string='Note')

    _sql_constraints = [
        ('unique_resource_week', 'UNIQUE(capacity_resource_id, week_date)',
         'Une seule ligne de capacité par affectation et par semaine.'),
    ]

    # ══════════════════════════════════════════════════════════════════════════
    # COMPUTES
    # ══════════════════════════════════════════════════════════════════════════

    @api.depends('week_date')
    def _compute_week_bounds(self):
        months_fr = ['jan.', 'fév.', 'mar.', 'avr.', 'mai', 'juin',
                     'juil.', 'aoû.', 'sep.', 'oct.', 'nov.', 'déc.']
        for rec in self:
            if not rec.week_date:
                rec.week_end_date = False
                rec.week_number = rec.week_label = ''
                continue
            d = rec.week_date
            end = d + timedelta(days=6)
            rec.week_end_date = end
            wnum = d.isocalendar()[1]
            rec.week_number = f'S{wnum:02d}'
            ms = months_fr[d.month - 1]
            me = months_fr[end.month - 1]
            if d.month == end.month:
                rec.week_label = f'S{wnum:02d} — {d.day} au {end.day} {me} {end.year}'
            else:
                rec.week_label = f'S{wnum:02d} — {d.day} {ms} au {end.day} {me} {end.year}'

    @api.depends('capacity_resource_id', 'week_date',
                 'override_calendar_id', 'allocation_rate')
    def _compute_capacity_standard(self):
        for rec in self:
            if not rec.capacity_resource_id or not rec.week_date:
                rec.capacity_standard = 0.0
                continue
            # Calendrier à utiliser : override_calendar > calendrier affectation
            calendar = rec.override_calendar_id or rec.resource_calendar_id
            if not calendar:
                rec.capacity_standard = 0.0
                continue
            try:
                dt_start, dt_end = rec._get_week_utc(calendar)
                # Capacité théorique du calendrier applicable, AVANT absences.
                # Les jours fériés / congés / maladies sont déduits séparément
                # dans _compute_absences, pour éviter les doubles déductions.
                hours = rec._work_hours_on_calendar(calendar, dt_start, dt_end)
                rate = (rec.allocation_rate or 100.0) / 100.0
                rec.capacity_standard = round(hours * rate, 2)
            except Exception as e:
                _logger.warning('[MrpCapacity] Erreur capacité standard [%s] : %s', rec.id, e)
                rec.capacity_standard = 0.0

    @api.depends('capacity_override', 'override_calendar_id')
    def _compute_is_overridden(self):
        for rec in self:
            rec.is_overridden = bool(rec.capacity_override > 0 or rec.override_calendar_id)

    @api.depends('capacity_resource_id', 'week_date', 'allocation_rate',
                 'override_calendar_id', 'resource_calendar_id', 'employee_id')
    def _compute_absences(self):
        for rec in self:
            if not rec.capacity_resource_id or not rec.week_date:
                rec.hours_public_holiday = 0.0
                rec.hours_leaves = 0.0
                rec.hours_sick = 0.0
                rec.hours_absence_total = 0.0
                continue

            calendar = rec.override_calendar_id or rec.resource_calendar_id
            if not calendar:
                rec.hours_public_holiday = 0.0
                rec.hours_leaves = 0.0
                rec.hours_sick = 0.0
                rec.hours_absence_total = 0.0
                continue

            dt_start, dt_end = rec._get_week_utc(calendar)
            rate = (rec.allocation_rate or 100.0) / 100.0
            employee = rec.employee_id

            # 1. Jours fériés / fermetures société.
            # Important : on compte uniquement les heures ouvrées impactées
            # par la fermeture, jamais la durée brute 00:00 → 23:59.
            h_holiday = 0.0
            holidays = self.env['resource.calendar.leaves'].search([
                ('calendar_id', '=', calendar.id),
                ('resource_id', '=', False),
                ('date_from', '<=', fields.Datetime.to_string(dt_end)),
                ('date_to', '>=', fields.Datetime.to_string(dt_start)),
            ])
            public_periods = []
            for h in holidays:
                leave_start = max(h.date_from, dt_start)
                leave_end = min(h.date_to, dt_end)
                if leave_start < leave_end:
                    public_periods.append((leave_start, leave_end))
                    h_holiday += rec._work_hours_on_calendar(calendar, leave_start, leave_end)

            # 2. Arrêts maladie validés.
            h_sick = 0.0
            sick_types = self.env['hr.leave.type']
            if employee:
                sick_types = self.env['hr.leave.type'].search([
                    '|',
                    ('time_type', '=', 'sick'),
                    ('name', 'ilike', 'maladie'),
                ])
                if sick_types:
                    sick_leaves = self.env['hr.leave'].search([
                        ('employee_id', '=', employee.id),
                        ('state', '=', 'validate'),
                        ('holiday_status_id', 'in', sick_types.ids),
                        ('date_from', '<=', fields.Datetime.to_string(dt_end)),
                        ('date_to', '>=', fields.Datetime.to_string(dt_start)),
                    ])
                    for s in sick_leaves:
                        leave_start = max(s.date_from, dt_start)
                        leave_end = min(s.date_to, dt_end)
                        if leave_start < leave_end:
                            # On exclut les jours fériés pour éviter de déduire deux fois.
                            h_sick += rec._work_hours_on_calendar(
                                calendar, leave_start, leave_end,
                                exclude_periods=public_periods,
                            )

            # 3. Congés validés hors maladie.
            h_leave = 0.0
            if employee:
                leave_domain = [
                    ('employee_id', '=', employee.id),
                    ('state', '=', 'validate'),
                    ('date_from', '<=', fields.Datetime.to_string(dt_end)),
                    ('date_to', '>=', fields.Datetime.to_string(dt_start)),
                ]
                if sick_types:
                    leave_domain.append(('holiday_status_id', 'not in', sick_types.ids))
                else:
                    leave_domain.append(('holiday_status_id.time_type', '!=', 'sick'))

                leaves = self.env['hr.leave'].search(leave_domain)
                for l in leaves:
                    leave_start = max(l.date_from, dt_start)
                    leave_end = min(l.date_to, dt_end)
                    if leave_start < leave_end:
                        # On exclut les jours fériés pour éviter de déduire deux fois.
                        h_leave += rec._work_hours_on_calendar(
                            calendar, leave_start, leave_end,
                            exclude_periods=public_periods,
                        )

            rec.hours_public_holiday = round(h_holiday * rate, 2)
            rec.hours_leaves = round(h_leave * rate, 2)
            rec.hours_sick = round(h_sick * rate, 2)
            rec.hours_absence_total = round((h_holiday + h_leave + h_sick) * rate, 2)

    @api.depends('capacity_standard', 'capacity_override', 'hours_absence_total')
    def _compute_capacity_net(self):
        for rec in self:
            base = rec.capacity_override if rec.capacity_override > 0.0 \
                else rec.capacity_standard
            rec.capacity_net = round(max(0.0, base - rec.hours_absence_total), 2)

    @api.depends('capacity_net', 'hours_planned')
    def _compute_delta(self):
        for rec in self:
            rec.delta = round(rec.capacity_net - rec.hours_planned, 2)

    @api.depends('employee_id', 'workcenter_id', 'week_label')
    def _compute_display_name(self):
        for rec in self:
            emp = rec.employee_id.name or '?'
            wc = rec.workcenter_id.name or '?'
            week = rec.week_label or '?'
            rec.display_name = f'{emp} / {wc} — {week}'

    def _compute_color(self):
        for rec in self:
            if rec.delta < -0.01:
                rec.color = 1    # Rouge = surcharge
            elif rec.is_overridden:
                rec.color = 3    # Orange = override calendrier ou manuel
            elif rec.hours_absence_total > 0:
                rec.color = 4    # Jaune = absences
            else:
                rec.color = 10   # Vert = normal

    # ══════════════════════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _get_week_utc(self, calendar=None):
        """Retourne (lundi 00:00 UTC, dimanche 23:59:59 UTC)."""
        cal = calendar or self.resource_calendar_id
        tz_name = (cal.tz if cal else None) or 'UTC'
        try:
            tz = pytz.timezone(tz_name)
        except Exception:
            tz = pytz.utc
        monday = datetime.combine(self.week_date, time(0, 0, 0))
        sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
        monday_utc = tz.localize(monday).astimezone(pytz.utc).replace(tzinfo=None)
        sunday_utc = tz.localize(sunday).astimezone(pytz.utc).replace(tzinfo=None)
        return monday_utc, sunday_utc

    def _as_utc_naive(self, value):
        """Convertit un datetime aware/naive en UTC naive pour les comparaisons."""
        if not value:
            return value
        if value.tzinfo:
            return value.astimezone(pytz.utc).replace(tzinfo=None)
        return value

    def _work_intervals_on_calendar(self, calendar, dt_start, dt_end):
        """
        Retourne les intervalles de travail du calendrier entre dt_start/dt_end,
        sans tenir compte des congés publics. Les absences sont calculées ensuite.
        """
        if not calendar or not dt_start or not dt_end or dt_start >= dt_end:
            return []
        try:
            tz = pytz.timezone(calendar.tz or 'UTC')
            start_aware = pytz.utc.localize(dt_start).astimezone(tz) if not dt_start.tzinfo else dt_start.astimezone(tz)
            end_aware = pytz.utc.localize(dt_end).astimezone(tz) if not dt_end.tzinfo else dt_end.astimezone(tz)

            try:
                intervals_batch = calendar._work_intervals_batch(
                    start_aware, end_aware, compute_leaves=False,
                )
            except TypeError:
                # Compatibilité si la signature locale ne supporte pas compute_leaves.
                intervals_batch = calendar._attendance_intervals_batch(start_aware, end_aware)

            result = []
            for _key, interval_list in intervals_batch.items():
                for start, stop, _meta in interval_list:
                    start_utc = self._as_utc_naive(start)
                    stop_utc = self._as_utc_naive(stop)
                    if stop_utc > start_utc:
                        result.append((start_utc, stop_utc))
            return result
        except Exception as e:
            _logger.warning('[MrpCapacity] Erreur intervalles calendrier [%s] : %s', calendar.display_name, e)
            return []

    def _work_hours_on_calendar(self, calendar, dt_start, dt_end, exclude_periods=None):
        """
        Calcule les heures ouvrées impactées par une période.
        - Utilise les horaires du calendrier applicable à la ressource/semaine.
        - Ne compte jamais les durées brutes type 00:00 → 23:59.
        - exclude_periods permet d'éviter les doubles déductions
          ex : congé personnel qui tombe pendant un jour férié.
        """
        if not calendar or not dt_start or not dt_end or dt_start >= dt_end:
            return 0.0

        exclude_periods = exclude_periods or []
        total_seconds = 0.0
        for work_start, work_end in self._work_intervals_on_calendar(calendar, dt_start, dt_end):
            start = max(work_start, dt_start)
            end = min(work_end, dt_end)
            if end <= start:
                continue
            seconds = (end - start).total_seconds()
            for ex_start, ex_end in exclude_periods:
                ex_s = max(start, ex_start)
                ex_e = min(end, ex_end)
                if ex_e > ex_s:
                    seconds -= (ex_e - ex_s).total_seconds()
            total_seconds += max(0.0, seconds)
        return total_seconds / 3600.0

    def _compute_calendar_hours(self, calendar, dt_start, dt_end):
        """
        Compatibilité ancienne méthode : retourne les heures ouvrées du calendrier
        avant absences. Conserve le nom pour les autres appels éventuels.
        """
        return self._work_hours_on_calendar(calendar, dt_start, dt_end)

    def _compute_hours_from_attendance(self, calendar):
        """
        Fallback : calcule les heures depuis les lignes d'attendance du calendrier.
        Compatible toutes versions Odoo.
        """
        if not calendar or not self.week_date:
            return 0.0
        total = 0.0
        # Récupère les lignes de présence (lundi=0 ... vendredi=4)
        week_day = self.week_date.weekday()  # 0 = lundi
        for attendance in calendar.attendance_ids:
            # dayofweek est un char '0'..'6'
            day_num = int(attendance.dayofweek)
            # Vérifie que ce jour tombe dans la semaine
            day_date = self.week_date + timedelta(days=(day_num - week_day) % 7)
            end_date = self.week_date + timedelta(days=6)
            if day_date > end_date:
                continue
            # hour_from et hour_to sont des floats (ex: 8.0 = 8h00, 12.5 = 12h30)
            total += attendance.hour_to - attendance.hour_from
        return total

    @staticmethod
    def _overlap_hours(d_from, d_to, week_start, week_end):
        if not d_from or not d_to:
            return 0.0
        start = max(d_from, week_start)
        end = min(d_to, week_end)
        if end > start:
            return (end - start).total_seconds() / 3600.0
        return 0.0

    @staticmethod
    def _overlap_seconds(d_from, d_to, week_start, week_end):
        if not d_from or not d_to:
            return 0.0
        start = max(d_from, week_start)
        end = min(d_to, week_end)
        if end > start:
            return (end - start).total_seconds()
        return 0.0

    def _leave_hours_in_week(self, leave, week_start, week_end):
        """
        Retourne les heures ouvrées du congé dans la semaine,
        basé sur le nombre de jours du congé × heures/jour du calendrier du POSTE.

        number_of_hours_display d'Odoo utilise le calendrier RH de l'employé
        qui peut être différent du calendrier du poste → on recalcule.
        """
        if not leave.date_from or not leave.date_to:
            return 0.0

        # Heures par jour travaillé selon le calendrier du poste
        calendar = self.resource_calendar_id
        hours_per_day = self._get_hours_per_day(calendar)

        # Nombre de jours ouvrés du congé qui tombent dans la semaine
        # On itère jour par jour entre max(leave_start, week_start) et min(leave_end, week_end)
        overlap_start = max(leave.date_from.date(), week_start.date() if hasattr(week_start, 'date') else week_start)
        overlap_end = min(leave.date_to.date(), week_end.date() if hasattr(week_end, 'date') else week_end)

        if overlap_end < overlap_start:
            return 0.0

        # Jours ouvrés du calendrier dans la période de chevauchement
        worked_days = set(int(a.dayofweek) for a in calendar.attendance_ids) if calendar else {0, 1, 2, 3, 4}

        from datetime import timedelta as td, date as date_type
        # Convertir en date si nécessaire
        if hasattr(overlap_start, 'date'):
            overlap_start = overlap_start.date()
        if hasattr(overlap_end, 'date'):
            overlap_end = overlap_end.date()

        days_count = 0
        current = overlap_start
        while current <= overlap_end:
            if current.weekday() in worked_days:
                days_count += 1
            current += td(days=1)

        result = round(days_count * hours_per_day, 2)
        _logger.debug(
            '[MrpCapacity] Congé %s: %d jours ouvrés × %.2fH/j = %.2fH cette semaine',
            leave.holiday_status_id.name, days_count, hours_per_day, result
        )
        return result

    def _get_hours_per_day(self, calendar):
        """Calcule les heures moyennes par jour travaillé depuis le calendrier."""
        if not calendar or not calendar.attendance_ids:
            return 7.8  # Fallback 39H/5j
        # Heures par jour de la semaine
        hours_by_day = {}
        for att in calendar.attendance_ids:
            day = int(att.dayofweek)
            hours_by_day[day] = hours_by_day.get(day, 0) + (att.hour_to - att.hour_from)
        if not hours_by_day:
            return 7.8
        return sum(hours_by_day.values()) / len(hours_by_day)

    # ══════════════════════════════════════════════════════════════════════════
    # ACTIONS
    # ══════════════════════════════════════════════════════════════════════════

    def action_reset_override(self):
        self.ensure_one()
        self.capacity_override = 0.0
        self.override_calendar_id = False

    def action_recompute(self):
        self.ensure_one()
        self._compute_capacity_standard()
        self._compute_absences()
        self._compute_capacity_net()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': 'Semaine recalculée avec succès.',
                'type': 'success',
                'sticky': False,
            },
        }

    @api.model
    def cron_recompute_absences(self):
        today = fields.Date.today()
        records = self.search([('week_date', '>=', today)])
        if records:
            records._compute_absences()
            records._compute_capacity_net()
            _logger.info('[MrpCapacity] Cron recalcul : %d lignes mises à jour', len(records))
