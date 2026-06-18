# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_laquage_supplier = fields.Boolean(
        string='Sous-traitant laquage',
        help='Cochez cette case pour proposer ce fournisseur dans le wizard de planification laquage F2M.',
    )
    laquage_product_id = fields.Many2one(
        'product.product',
        string='Article de service laquage',
        domain=[('purchase_ok', '=', True), ('type', '=', 'service')],
        help="Article de service acheté utilisé pour créer le bon de commande fournisseur de laquage.",
    )
    laquage_price_unit = fields.Float(string='Prix laquage unitaire')
    laquage_qty_field_name = fields.Char(
        string='Champ quantité/m² sur OF',
        help="Optionnel. Nom technique d'un champ OF contenant la surface/quantité à acheter. Si vide, Odoo utilise la quantité de l'OF.",
    )
    laquage_slot_ids = fields.One2many('fma.laquage.slot', 'partner_id', string='Créneaux laquage')


class FmaLaquageSlot(models.Model):
    _name = 'fma.laquage.slot'
    _description = 'Créneau laquage sous-traitant'
    _order = 'partner_id, departure_weekday, return_week_offset, return_weekday'

    partner_id = fields.Many2one('res.partner', string='Fournisseur', required=True, ondelete='cascade', domain=[('is_laquage_supplier', '=', True)])
    name = fields.Char(compute='_compute_name', store=True)
    active = fields.Boolean(default=True)
    departure_weekday = fields.Selection([
        ('0', 'Lundi'), ('1', 'Mardi'), ('2', 'Mercredi'), ('3', 'Jeudi'),
        ('4', 'Vendredi'), ('5', 'Samedi'), ('6', 'Dimanche')
    ], string='Jour départ', required=True)
    return_weekday = fields.Selection([
        ('0', 'Lundi'), ('1', 'Mardi'), ('2', 'Mercredi'), ('3', 'Jeudi'),
        ('4', 'Vendredi'), ('5', 'Samedi'), ('6', 'Dimanche')
    ], string='Jour retour', required=True)
    return_week_offset = fields.Integer(
        string='Décalage semaine retour',
        default=0,
        help='0 = même semaine si possible. 1 = semaine suivante. Exemple mercredi → lundi suivant = 1.',
    )
    duration_days = fields.Integer(compute='_compute_duration_days', store=True)

    @api.depends('departure_weekday', 'return_weekday', 'return_week_offset')
    def _compute_duration_days(self):
        for rec in self:
            if rec.departure_weekday is False or rec.return_weekday is False:
                rec.duration_days = 0
                continue
            dep = int(rec.departure_weekday)
            ret = int(rec.return_weekday)
            delta = (ret - dep) % 7
            rec.duration_days = delta + (7 * int(rec.return_week_offset or 0))

    @api.depends('partner_id.name', 'departure_weekday', 'return_weekday', 'return_week_offset')
    def _compute_name(self):
        labels = dict(self._fields['departure_weekday'].selection)
        for rec in self:
            dep = labels.get(rec.departure_weekday, '')
            ret = labels.get(rec.return_weekday, '')
            suffix = ' +%s sem.' % rec.return_week_offset if rec.return_week_offset else ''
            rec.name = '%s : %s → %s%s' % (rec.partner_id.name or '', dep, ret, suffix)

    @api.constrains('return_week_offset')
    def _check_return_week_offset(self):
        for rec in self:
            if rec.return_week_offset < 0:
                raise ValidationError(_('Le décalage semaine retour ne peut pas être négatif.'))
