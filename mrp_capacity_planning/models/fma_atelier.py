# -*- coding: utf-8 -*-
from odoo import api, fields, models


class FmaAtelier(models.Model):
    _name = 'fma.atelier'
    _description = 'Atelier de production FMA'
    _order = 'sequence, name'
    _rec_name = 'name'

    name = fields.Char(string='Atelier', required=True)
    code = fields.Char(string='Code', index=True)
    sequence = fields.Integer(string='Séquence', default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer(string='Couleur')
    calendar_id = fields.Many2one(
        'resource.calendar',
        string='Calendrier atelier',
        help='Calendrier théorique de l’atelier. Informatif au départ : la capacité reste calculée depuis les affectations employés.'
    )
    responsible_id = fields.Many2one('hr.employee', string='Responsable')
    note = fields.Text(string='Note')

    display_name = fields.Char(compute='_compute_display_name', store=True)

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = '[%s] %s' % (rec.code, rec.name) if rec.code else rec.name
