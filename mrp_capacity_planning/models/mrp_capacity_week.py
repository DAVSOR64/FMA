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
                hours = rec._compute_calendar_hours(calendar, dt_start, dt_end)
                rate = (rec.allocation_rate or 100.0) / 100.0
                rec.capacity_standard = round(hours * rate, 2)
            except Exception as e:
                _logger.warning('[MrpCapacity] Erreur capacité standard [%s] : %s', rec.id, e)
                rec.capacity_standard = 0.0

    @api.depends('capacity_override', 'override_calendar_id')
    def _compute_is_overridden(self):
        for rec in self:
            rec.is_overridden = bool(rec.capacity_override > 0 or rec.override_calendar_id)

    @api.depends('capacity_resource_id', 'week_date', 'allocation_rate')
    def _compute_absences(self):
        for rec in self:
            if not rec.capacity_resource_id or not rec.week_date:
                rec.hours_public_holiday = 0.0
                rec.hours_leaves = 0.0
                rec.hours_sick = 0.0
                rec.hours_absence_total = 0.0
                continue

            calendar = rec.override_calendar_id or rec.resource_calendar_id
            dt_start, dt_end = rec._get_week_utc(calendar)
            rate = (rec.allocation_rate or 100.0) / 100.0
            employee = rec.employee_id

            # 1. Jours fériés société
            h_holiday = 0.0
            if calendar:
                holidays = self.env['resource.calendar.leaves'].search([
                    ('calendar_id', '=', calendar.id),
                    ('resource_id', '=', False),
                    ('date_from', '<=', fields.Datetime.to_string(dt_end)),
                    ('date_to', '>=', fields.Datetime.to_string(dt_start)),
                ])
                for h in holidays:
                    h_holiday += self._overlap_hours(h.date_from, h.date_to, dt_start, dt_end)

            # 2. Congés validés (tous types sauf maladie)
            h_leave = 0.0
            if employee:
                leaves = self.env['hr.leave'].search([
                    ('employee_id', '=', employee.id),
                    ('state', '=', 'validate'),
                    ('holiday_status_id.time_type', 'not in', ['sick']),
                    ('date_from', '<=', fields.Datetime.to_string(dt_end)),
                    ('date_to', '>=', fields.Datetime.to_string(dt_start)),
                ])
                for l in leaves:
                    overlap = self._overlap_hours(l.date_from, l.date_to, dt_start, dt_end)
                    _logger.info('[MrpCapacity] Congé %s: %s → %s, overlap=%.2fH (semaine %s → %s)',
                                 l.holiday_status_id.name, l.date_from, l.date_to,
                                 overlap, dt_start, dt_end)
                    h_leave += overlap

            # 3. Arrêts maladie (time_type = sick OU catégorie contient 'maladie')
            h_sick = 0.0
            if employee:
                sick_types = self.env['hr.leave.type'].search([
                    '|',
                    ('time_type', '=', 'sick'),
                    ('name', 'ilike', 'maladie'),
                ])
                _logger.info('[MrpCapacity] Types maladie trouvés: %s', sick_types.mapped('name'))
                sick_domain = [
                    ('employee_id', '=', employee.id),
                    ('state', '=', 'validate'),
                    ('date_from', '<=', fields.Datetime.to_string(dt_end)),
                    ('date_to', '>=', fields.Datetime.to_string(dt_start)),
                ]
                if sick_types:
                    sick_domain.append(('holiday_status_id', 'in', sick_types.ids))
                    sick_leaves = self.env['hr.leave'].search(sick_domain)
                    for s in sick_leaves:
                        overlap = self._overlap_hours(s.date_from, s.date_to, dt_start, dt_end)
                        _logger.info('[MrpCapacity] Maladie %s: %s → %s, overlap=%.2fH',
                                     s.holiday_status_id.name, s.date_from, s.date_to, overlap)
                        h_sick += overlap
                    h_leave = max(0.0, h_leave - h_sick)

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

    def _compute_calendar_hours(self, calendar, dt_start, dt_end):
        """
        Calcule les heures de travail brutes sur la période.
        Compatible Odoo 17 — utilise _work_intervals_batch.
        """
        try:
            # Méthode Odoo 17 : _work_intervals_batch
            # Retourne un dict {resource_id: Intervals}
            # Sans ressource = on passe None pour avoir le calendrier brut
            tz = pytz.timezone(calendar.tz or 'UTC')
            dt_start_tz = pytz.utc.localize(dt_start).astimezone(tz)
            dt_end_tz = pytz.utc.localize(dt_end).astimezone(tz)

            intervals = calendar._work_intervals_batch(
                dt_start_tz, dt_end_tz,
            )
            # intervals est un dict, la clé False ou 0 = pas de ressource spécifique
            total_hours = 0.0
            for key, interval_list in intervals.items():
                for start, stop, _meta in interval_list:
                    total_hours += (stop - start).total_seconds() / 3600.0
            return total_hours
        except Exception as e:
            _logger.warning('[MrpCapacity] _work_intervals_batch failed: %s — fallback', e)
            # Fallback : calcul manuel depuis les attendance lines du calendrier
            return self._compute_hours_from_attendance(calendar)

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
