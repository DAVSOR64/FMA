# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MrpCapacityGenerateWizard(models.TransientModel):
    _name = 'mrp.capacity.generate.wizard'
    _description = 'Générer les semaines de capacité'

    date_from = fields.Date(
        string='Première semaine',
        required=True,
        default=lambda self: fields.Date.today(),
    )
    date_to = fields.Date(
        string='Dernière semaine',
        required=True,
        default=lambda self: fields.Date.today() + timedelta(weeks=12),
    )
    capacity_resource_ids = fields.Many2many(
        'mrp.capacity.resource',
        string='Affectations',
        help='Laisser vide = toutes les affectations actives',
    )
    overwrite_existing = fields.Boolean(
        string='Recalculer les semaines existantes',
        default=False,
    )
    weeks_count = fields.Integer(
        string='Nombre de semaines',
        compute='_compute_weeks_count',
    )

    @api.depends('date_from', 'date_to')
    def _compute_weeks_count(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_to >= rec.date_from:
                delta = (rec.date_to - rec.date_from).days
                rec.weeks_count = delta // 7 + 1
            else:
                rec.weeks_count = 0

    @api.onchange('date_from')
    def _onchange_date_from(self):
        if self.date_from:
            d = self.date_from
            self.date_from = d - timedelta(days=d.weekday())

    @api.onchange('date_to')
    def _onchange_date_to(self):
        if self.date_to:
            d = self.date_to
            self.date_to = d - timedelta(days=d.weekday())

    def action_generate(self):
        self.ensure_one()
        if not self.date_from or not self.date_to:
            raise UserError('Veuillez renseigner les dates.')
        if self.date_from > self.date_to:
            raise UserError('La date de début doit être avant la date de fin.')

        if self.capacity_resource_ids:
            resources = self.capacity_resource_ids
        else:
            resources = self.env['mrp.capacity.resource'].search([('active', '=', True)])

        if not resources:
            raise UserError(
                'Aucune affectation trouvée. '
                'Créez d\'abord des affectations dans "Ressources & Postes".'
            )

        current = self.date_from - timedelta(days=self.date_from.weekday())
        end_monday = self.date_to - timedelta(days=self.date_to.weekday())

        created = 0
        updated = 0

        while current <= end_monday:
            week_end = current + timedelta(days=6)
            for res in resources:
                if res.date_start and res.date_start > week_end:
                    continue
                if res.date_end and res.date_end < current:
                    continue

                existing = self.env['mrp.capacity.week'].search([
                    ('capacity_resource_id', '=', res.id),
                    ('week_date', '=', current),
                ], limit=1)

                if existing:
                    if self.overwrite_existing:
                        existing._compute_capacity_standard()
                        existing._compute_absences()
                        existing._compute_capacity_net()
                        updated += 1
                else:
                    self.env['mrp.capacity.week'].create({
                        'capacity_resource_id': res.id,
                        'week_date': current,
                    })
                    created += 1

            current += timedelta(weeks=1)

        # Retourne directement la vue planning — pas de display_notification imbriqué
        return {
            'type': 'ir.actions.act_window',
            'name': 'Capacité hebdomadaire',
            'res_model': 'mrp.capacity.week',
            'view_mode': 'gantt,list,form',
            'views': [(False, 'gantt'), (False, 'list'), (False, 'form')],
            'context': {'search_default_future': 1},
            'target': 'current',
        }
