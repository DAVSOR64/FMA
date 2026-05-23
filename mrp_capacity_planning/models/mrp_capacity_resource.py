# -*- coding: utf-8 -*-
"""
mrp.capacity.resource
=====================
Affectation Ressource (employé) ↔ Poste de travail.

Le calendrier est choisi ici — il peut être différent du calendrier
par défaut de l'employé (ex: un employé à 35H affecté à un poste 39H).
Il est modifiable à tout moment : les semaines futures se recalculeront.
"""
import logging
from datetime import timedelta
from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class MrpCapacityResource(models.Model):
    _name = 'mrp.capacity.resource'
    _description = 'Affectation ressource → poste de travail'
    _order = 'workcenter_id, employee_id'
    _rec_name = 'display_name'

    # ── Ressource ──────────────────────────────────────────────────────────────
    employee_id = fields.Many2one(
        'hr.employee',
        string='Ressource (employé)',
        required=True,
        index=True,
        ondelete='cascade',
    )
    resource_id = fields.Many2one(
        related='employee_id.resource_id',
        store=True,
        string='Ressource technique',
    )

    # ── Calendrier — choisi ici, indépendant du calendrier RH de l'employé ────
    resource_calendar_id = fields.Many2one(
        'resource.calendar',
        string='Calendrier de travail',
        required=True,
        help='Calendrier appliqué à ce poste pour cette ressource. '
             'Peut être différent du calendrier RH de l\'employé. '
             'Ex: employé à 35H mais affecté à un poste 39H ou 43H.',
    )

    # ── Poste de travail ───────────────────────────────────────────────────────
    workcenter_id = fields.Many2one(
        'mrp.workcenter',
        string='Poste de travail',
        required=True,
        index=True,
        ondelete='cascade',
    )

    # ── Taux d'affectation ─────────────────────────────────────────────────────
    allocation_rate = fields.Float(
        string='Taux d\'affectation (%)',
        default=100.0,
        digits=(5, 1),
        help='100% = ressource dédiée à ce poste. '
             '50% = partage son temps entre deux postes.',
    )

    # ── Validité ───────────────────────────────────────────────────────────────
    date_start = fields.Date(string='Date de début')
    date_end = fields.Date(string='Date de fin')
    active = fields.Boolean(default=True)
    note = fields.Text(string='Note')

    # ── Computed ───────────────────────────────────────────────────────────────
    display_name = fields.Char(compute='_compute_display_name', store=True)
    capacity_week_count = fields.Integer(
        string='Semaines planifiées',
        compute='_compute_capacity_week_count',
    )

    @api.depends('employee_id', 'workcenter_id', 'allocation_rate', 'resource_calendar_id')
    def _compute_display_name(self):
        for rec in self:
            emp = rec.employee_id.name or '?'
            wc = rec.workcenter_id.name or '?'
            cal = rec.resource_calendar_id.name or '?'
            rate = f' — {int(rec.allocation_rate)}%' if rec.allocation_rate != 100 else ''
            rec.display_name = f'{emp} → {wc} [{cal}]{rate}'

    def _compute_capacity_week_count(self):
        for rec in self:
            rec.capacity_week_count = self.env['mrp.capacity.week'].search_count([
                ('capacity_resource_id', '=', rec.id),
            ])

    # ── Onchange : pré-remplit le calendrier depuis l'employé ─────────────────
    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id and self.employee_id.resource_calendar_id:
            self.resource_calendar_id = self.employee_id.resource_calendar_id

    # ── Contraintes ────────────────────────────────────────────────────────────
    @api.constrains('allocation_rate')
    def _check_allocation_rate(self):
        for rec in self:
            if not (0 < rec.allocation_rate <= 100):
                raise ValidationError('Le taux d\'affectation doit être entre 1% et 100%.')

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_start > rec.date_end:
                raise ValidationError('La date de début doit être avant la date de fin.')

    # ── Recalcul automatique quand le calendrier change ────────────────────────
    # ── Génération automatique des semaines à la sauvegarde ───────────────────
    @api.model
    def create(self, vals):
        rec = super().create(vals)
        rec._auto_generate_weeks()
        return rec

    def write(self, vals):
        res = super().write(vals)
        if 'resource_calendar_id' in vals or 'allocation_rate' in vals:
            today = fields.Date.today()
            weeks = self.env['mrp.capacity.week'].search([
                ('capacity_resource_id', 'in', self.ids),
                ('week_date', '>=', today),
            ])
            if weeks:
                weeks._compute_capacity_standard()
                weeks._compute_capacity_net()
                _logger.info(
                    '[MrpCapacity] Recalcul %d semaines après changement calendrier', len(weeks)
                )
        # Si les dates changent, regénère les semaines manquantes
        if any(k in vals for k in ('date_start', 'date_end', 'active')):
            self._auto_generate_weeks()
        return res

    def _auto_generate_weeks(self):
        """
        Génère automatiquement les semaines manquantes pour cette affectation.
        - Si date_start et date_end sont définies → génère sur cette plage
        - Sinon → génère sur les 12 prochaines semaines par défaut
        """
        today = fields.Date.today()
        for rec in self:
            if not rec.active:
                continue
            # Déterminer la plage
            if rec.date_start and rec.date_end:
                date_from = rec.date_start
                date_end = rec.date_end
            elif rec.date_start:
                date_from = rec.date_start
                date_end = date_from + timedelta(weeks=52)
            else:
                date_from = today
                date_end = today + timedelta(weeks=12)

            # Force lundi
            date_from = date_from - timedelta(days=date_from.weekday())
            date_end = date_end - timedelta(days=date_end.weekday())

            current = date_from
            created = 0
            while current <= date_end:
                existing = self.env['mrp.capacity.week'].search([
                    ('capacity_resource_id', '=', rec.id),
                    ('week_date', '=', current),
                ], limit=1)
                if not existing:
                    self.env['mrp.capacity.week'].create({
                        'capacity_resource_id': rec.id,
                        'week_date': current,
                    })
                    created += 1
                current += timedelta(weeks=1)

            if created:
                _logger.info(
                    '[MrpCapacity] Auto-génération : %d semaines créées pour %s',
                    created, rec.display_name
                )

    # ── Actions ────────────────────────────────────────────────────────────────
    def action_view_capacity_weeks(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Semaines — {self.display_name}',
            'res_model': 'mrp.capacity.week',
            'view_mode': 'gantt,list,form',
            'domain': [('capacity_resource_id', '=', self.id)],
            'context': {'default_capacity_resource_id': self.id},
        }

    def action_generate_weeks(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Générer les semaines',
            'res_model': 'mrp.capacity.generate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_capacity_resource_ids': [(4, self.id)],
            },
        }
