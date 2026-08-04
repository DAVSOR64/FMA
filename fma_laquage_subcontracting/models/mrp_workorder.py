# -*- coding: utf-8 -*-
from odoo import models, fields, api


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    is_external_laquage = fields.Boolean(
        string='Laquage externe',
        copy=False,
        help="Cette opération représente un délai de sous-traitance. Elle ne consomme pas de capacité interne.",
    )
    laquage_state = fields.Selection([
        ('none', 'Non concerné'),
        ('to_plan', 'À planifier'),
        ('planned', 'Planifié'),
        ('sent', 'Envoyé'),
        ('returned', 'Retourné'),
    ], string='État laquage', default='none', copy=False)
    laquage_departure_planned = fields.Datetime(string='Départ laquage prévu', copy=False)
    laquage_return_planned = fields.Datetime(string='Retour laquage prévu', copy=False)
    laquage_departure_real = fields.Datetime(string='Départ laquage réel', copy=False)
    laquage_return_real = fields.Datetime(string='Retour laquage réel', copy=False)

    @api.depends('workcenter_id', 'name', 'operation_id', 'operation_id.sequence', 'is_external_laquage')
    def _compute_color_index(self):
        super()._compute_color_index()
        for wo in self.filtered('is_external_laquage'):
            wo.color_index = 8
