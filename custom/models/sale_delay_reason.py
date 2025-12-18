# -*- coding: utf-8 -*-
from odoo import models, fields


class SaleDelayReason(models.Model):
    _name = 'sale.delay.reason'
    _description = 'Motif de retard de livraison'
    _order = 'level, parent_id, name'

    name = fields.Char(string="Libellé", required=True)
    level = fields.Selection(
        [('1', 'Niveau 1'), ('2', 'Niveau 2')],
        string="Niveau",
        required=True,
        default='1'
    )
    parent_id = fields.Many2one(
        'sale.delay.reason',
        string="Motif Niv 1",
        domain=[('level', '=', '1')]
    )
    active = fields.Boolean(default=True)
