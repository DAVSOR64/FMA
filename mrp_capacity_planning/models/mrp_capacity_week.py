# -*- coding: utf-8 -*-
"""
mrp.capacity.week
=================
Une ligne = une ressource × une semaine × un poste de travail.

Calculs automatiques :
  - capacity_standard  : heures de travail brutes du calendrier (sans absences)
  - hours_public_holiday : jours fériés société (resource.calendar.leaves sans ressource)
  - hours_leaves       : congés validés de l'employé
  - hours_sick         : arrêts maladie validés
  - capacity_net       : (override si saisi, sinon standard) − total absences

Couleurs Gantt :
  10 = vert   → normal, pas de surcharge
   3 = orange → override manuel actif
   1 = rouge  → delta < 0 (surcharge)
"""
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

    # ── Raccourcis (stockés pour filtres/groupby rapides) ──────────────────────
    employee_id = fields.Many2one(
        related='capacity_resource_id.employee_id',
        store=True,
        string='Ressource',
        index=True,
    )
    workcenter_id = fields.Many2one(
        related='capacity_resource_id.workcenter_id',
        store=True,
        string='Poste de travail',
        index=True,
    )
    resource_calendar_id = fields.Many2one(
        related='capacity_resource_id.resource_calendar_id',
        store=True,
        string='Calendrier',
    )
    allocation_rate = fields.Float(
        related='capacity_resource_id.allocation_rate',
        store=True,
        string='Taux affectation (%)',
    )

    # ── Semaine ────────────────────────────────────────────────────────────────
    week_date = fields.Date(
        string='Semaine (lundi)',
        required=True,
        index=True,
    )
    week_end_date = fields.Date(
        string='Fin semaine',
        compute='_compute_week_bounds',
        store=True,
    )
    week_number = fields.Char(
        string='N° semaine',
        compute='_compute_week_bounds',
        store=True,
    )
    week_label = fields.Char(
        string='Semaine',
        compute='_compute_week_bounds',
        store=True,
        help='Ex: S08 — 17 au 23 fév. 2026',
    )

    # ── Capacité brute calendrier ──────────────────────────────────────────────
    capacity_standard = fields.Float(
        string='Standard (H)',
        compute='_compute_capacity_standard',
        store=True,
        digits=(6, 2),
    )

    # ── Override manuel ────────────────────────────────────────────────────────
    capacity_override = fields.Float(
        string='Manuel (H)',
        default=0.0,
        digits=(6, 2),
        help='Si > 0, remplace la capacité standard pour cette semaine uniquement.',
    )
    is_overridden = fields.Boolean(
        compute='_compute_is_overridden',
        store=True,
        string='Override actif',
    )

    # ── Absences automatiques ──────────────────────────────────────────────────
    hours_public_holiday = fields.Float(
        string='Jours fériés (H)',
        compute='_compute_absences',
        store=True,
        digits=(6, 2),
    )
    hours_leaves = fields.Float(
        string='Congés (H)',
        compute='_compute_absences',
        store=True,
        digits=(6, 2),
    )
    hours_sick = fields.Float(
        string='Maladie (H)',
        compute='_compute_absences',
        store=True,
        digits=(6, 2),
    )
    hours_absence_total = fields.Float(
        string='Total absences (H)',
        compute='_compute_absences',
        store=True,
        digits=(6, 2),
    )

    # ── Capacité nette ─────────────────────────────────────────────────────────
    capacity_net = fields.Float(
        string='Capacité nette (H)',
        compute='_compute_capacity_net',
        store=True,
        digits=(6, 2),
    )

    # ── Charge planifiée (à renseigner manuellement ou depuis macro_planning) ──
    hours_planned = fields.Float(
        string='Charge (H)',
        default=0.0,
        digits=(6, 2),
    )
    delta = fields.Float(
        string='Delta (H)',
        compute='_compute_delta',
        store=True,
        digits=(6, 2),
        help='Capacité nette − Charge planifiée. Négatif = surcharge.',
    )

    # ── Affichage / couleur ────────────────────────────────────────────────────
    display_name = fields.Char(
        compute='_compute_display_name',
        store=True,
    )
    color = fields.Integer(
        compute='_compute_color',
        string='Couleur',
    )
    note = fields.Char(string='Note')

    # ── Contrainte unicité ─────────────────────────────────────────────────────
    _sql_constraints = [
        (
            'unique_resource_week',
            'UNIQUE(capacity_resource_id, week_date)',
            'Une seule ligne de capacité par affectation et par semaine.',
        ),
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
                rec.week_number = ''
                rec.week_label = ''
                continue
            d = rec.week_date
            end = d + timedelta(days=6)
            rec.week_end_date = end
            wnum = d.isocalendar()[1]
            rec.week_number = f'S{wnum:02d}'
            m_start = months_fr[d.month - 1]
            m_end = months_fr[end.month - 1]
            if d.month == end.month:
                rec.week_label = f'S{wnum:02d} — {d.day} au {end.day} {m_end} {end.year}'
            else:
                rec.week_label = f'S{wnum:02d} — {d.day} {m_start} au {end.day} {m_end} {end.year}'

    @api.depends('capacity_resource_id', 'week_date', 'allocation_rate')
    def _compute_capacity_standard(self):
        for rec in self:
            if not rec.capacity_resource_id or not rec.week_date:
                rec.capacity_standard = 0.0
                continue
            try:
                dt_start, dt_end = rec._get_week_utc()
                calendar = rec.resource_calendar_id
                if not calendar:
                    rec.capacity_standard = 0.0
                    continue
                # Calcul des heures brutes du calendrier (sans déduire les absences)
                work_data = calendar._get_work_duration_data(
                    dt_start, dt_end,
                    compute_leaves=False,
                )
                hours_brut = work_data.get('hours', 0.0)
                # Applique le taux d'affectation
                rate = (rec.allocation_rate or 100.0) / 100.0
                rec.capacity_standard = round(hours_brut * rate, 2)
            except Exception as e:
                _logger.warning('[MrpCapacity] Erreur capacité standard [%s] : %s', rec.id, e)
                rec.capacity_standard = 0.0

    @api.depends('capacity_override')
    def _compute_is_overridden(self):
        for rec in self:
            rec.is_overridden = rec.capacity_override > 0.0

    @api.depends('capacity_resource_id', 'week_date', 'allocation_rate')
    def _compute_absences(self):
        for rec in self:
            if not rec.capacity_resource_id or not rec.week_date:
                rec.hours_public_holiday = 0.0
                rec.hours_leaves = 0.0
                rec.hours_sick = 0.0
                rec.hours_absence_total = 0.0
                continue

            dt_start, dt_end = rec._get_week_utc()
            rate = (rec.allocation_rate or 100.0) / 100.0
            calendar = rec.resource_calendar_id
            employee = rec.employee_id

            # ── 1. Jours fériés société ──────────────────────────────────────
            # resource.calendar.leaves sans resource_id = fériés globaux société
            h_holiday = 0.0
            if calendar:
                holidays = self.env['resource.calendar.leaves'].search([
                    ('calendar_id', '=', calendar.id),
                    ('resource_id', '=', False),
                    ('date_from', '<=', fields.Datetime.to_string(dt_end)),
                    ('date_to', '>=', fields.Datetime.to_string(dt_start)),
                ])
                for h in holidays:
                    h_holiday += rec._overlap_hours(h.date_from, h.date_to, dt_start, dt_end)

            # ── 2. Congés validés (hors maladie) ────────────────────────────
            h_leave = 0.0
            if employee:
                leaves = self.env['hr.leave'].search([
                    ('employee_id', '=', employee.id),
                    ('state', '=', 'validate'),
                    ('holiday_status_id.time_type', 'in', ['leave', 'other']),
                    ('date_from', '<=', fields.Datetime.to_string(dt_end)),
                    ('date_to', '>=', fields.Datetime.to_string(dt_start)),
                ])
                for l in leaves:
                    h_leave += rec._overlap_hours(l.date_from, l.date_to, dt_start, dt_end)

            # ── 3. Arrêts maladie ────────────────────────────────────────────
            h_sick = 0.0
            if employee:
                sick_leaves = self.env['hr.leave'].search([
                    ('employee_id', '=', employee.id),
                    ('state', '=', 'validate'),
                    ('holiday_status_id.time_type', '=', 'sick'),
                    ('date_from', '<=', fields.Datetime.to_string(dt_end)),
                    ('date_to', '>=', fields.Datetime.to_string(dt_start)),
                ])
                for s in sick_leaves:
                    h_sick += rec._overlap_hours(s.date_from, s.date_to, dt_start, dt_end)

            # Applique le taux d'affectation sur les absences aussi
            rec.hours_public_holiday = round(h_holiday * rate, 2)
            rec.hours_leaves = round(h_leave * rate, 2)
            rec.hours_sick = round(h_sick * rate, 2)
            rec.hours_absence_total = round((h_holiday + h_leave + h_sick) * rate, 2)

    @api.depends(
        'capacity_standard', 'capacity_override', 'hours_absence_total'
    )
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
                rec.color = 3    # Orange = override actif
            elif rec.hours_absence_total > 0:
                rec.color = 4    # Jaune = absences cette semaine
            else:
                rec.color = 10   # Vert = tout va bien

    # ══════════════════════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _get_week_utc(self):
        """
        Retourne (lundi 00:00 UTC, dimanche 23:59:59 UTC)
        en tenant compte du fuseau horaire du calendrier.
        """
        calendar = self.resource_calendar_id
        tz_name = (calendar.tz if calendar else None) or 'UTC'
        try:
            tz = pytz.timezone(tz_name)
        except Exception:
            tz = pytz.utc

        monday = datetime.combine(self.week_date, time(0, 0, 0))
        sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)

        monday_utc = tz.localize(monday).astimezone(pytz.utc).replace(tzinfo=None)
        sunday_utc = tz.localize(sunday).astimezone(pytz.utc).replace(tzinfo=None)
        return monday_utc, sunday_utc

    @staticmethod
    def _overlap_hours(d_from, d_to, week_start, week_end):
        """Heures de chevauchement entre [d_from, d_to] et [week_start, week_end]."""
        if not d_from or not d_to:
            return 0.0
        start = max(d_from, week_start)
        end = min(d_to, week_end)
        if end > start:
            return (end - start).total_seconds() / 3600.0
        return 0.0

    # ══════════════════════════════════════════════════════════════════════════
    # ACTIONS BOUTONS
    # ══════════════════════════════════════════════════════════════════════════

    def action_reset_override(self):
        self.ensure_one()
        self.capacity_override = 0.0

    def action_recompute(self):
        """Recalcul forcé de cette ligne (absences + capacité nette)."""
        self.ensure_one()
        self._compute_capacity_standard()
        self._compute_absences()
        self._compute_capacity_net()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': 'Semaine recalculée.',
                'type': 'success',
                'sticky': False,
            },
        }

    # ══════════════════════════════════════════════════════════════════════════
    # TÂCHE PLANIFIÉE
    # ══════════════════════════════════════════════════════════════════════════

    @api.model
    def cron_recompute_absences(self):
        """Recalcule toutes les semaines futures (appelé par ir.cron)."""
        today = fields.Date.today()
        records = self.search([('week_date', '>=', today)])
        if records:
            records._compute_absences()
            records._compute_capacity_net()
            _logger.info(
                '[MrpCapacity] Recalcul absences planifié : %d lignes mises à jour',
                len(records)
            )
