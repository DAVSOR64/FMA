# -*- coding: utf-8 -*-
from odoo import fields, models


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

    def name_get(self):
        result = []
        for rec in self:
            name = '[%s] %s' % (rec.code, rec.name) if rec.code else rec.name
            result.append((rec.id, name))
        return result
