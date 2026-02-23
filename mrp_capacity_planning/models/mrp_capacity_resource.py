# -*- coding: utf-8 -*-
"""
mrp.capacity.resource
=====================
Table de correspondance Ressource ↔ Poste de travail.

C'est ici qu'on déclare qu'un employé est affecté à un poste.
Un employé peut être affecté à plusieurs postes (avec des pourcentages).
Un poste peut avoir plusieurs ressources.
"""
import logging
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
    resource_calendar_id = fields.Many2one(
        related='employee_id.resource_calendar_id',
        store=True,
        string='Calendrier de travail',
        readonly=False,
    )

    # ── Poste de travail ───────────────────────────────────────────────────────
    workcenter_id = fields.Many2one(
        'mrp.workcenter',
        string='Poste de travail',
        required=True,
        index=True,
        ondelete='cascade',
    )

    # ── Paramètres d'affectation ───────────────────────────────────────────────
    allocation_rate = fields.Float(
        string='Taux d\'affectation (%)',
        default=100.0,
        digits=(5, 1),
        help='Pourcentage du temps de la ressource alloué à ce poste. '
             'Ex: 50% si la ressource partage son temps entre deux postes.',
    )
    date_start = fields.Date(
        string='Date de début',
        help='Laisser vide = sans limite de début',
    )
    date_end = fields.Date(
        string='Date de fin',
        help='Laisser vide = sans limite de fin',
    )
    active = fields.Boolean(default=True)
    note = fields.Text(string='Note')

    # ── Computed ───────────────────────────────────────────────────────────────
    display_name = fields.Char(
        compute='_compute_display_name',
        store=True,
    )
    capacity_week_count = fields.Integer(
        string='Semaines planifiées',
        compute='_compute_capacity_week_count',
    )

    @api.depends('employee_id', 'workcenter_id', 'allocation_rate')
    def _compute_display_name(self):
        for rec in self:
            emp = rec.employee_id.name or '?'
            wc = rec.workcenter_id.name or '?'
            rate = f' ({int(rec.allocation_rate)}%)' if rec.allocation_rate != 100 else ''
            rec.display_name = f'{emp} → {wc}{rate}'

    def _compute_capacity_week_count(self):
        for rec in self:
            rec.capacity_week_count = self.env['mrp.capacity.week'].search_count([
                ('capacity_resource_id', '=', rec.id),
            ])

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
        """Ouvre le wizard de génération pré-filtré sur cette ressource."""
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
