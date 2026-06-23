# -*- coding: utf-8 -*-
from odoo import models, fields


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    laquage_production_id = fields.Many2one(
        'mrp.production',
        string='OF laquage',
        copy=False,
        index=True,
        help="OF F2M à l'origine de cette commande de sous-traitance laquage.",
    )
    laquage_sent_date = fields.Datetime(
        string="Date envoi laquage",
        copy=False,
        help="Date réelle d'envoi chez le sous-traitant laquage.",
    )
    laquage_return_date = fields.Datetime(
        string="Date retour laquage",
        copy=False,
        help="Date réelle de retour du sous-traitant laquage.",
    )
    laquage_status = fields.Selection([
        ('to_send', 'À envoyer'),
        ('sent', 'Chez le laqueur'),
        ('returned', 'Revenu'),
    ], string="Statut laquage", copy=False, default='to_send')


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    laquage_production_id = fields.Many2one(
        'mrp.production',
        string='OF laquage',
        copy=False,
        index=True,
        help="OF F2M à l'origine de cette ligne de sous-traitance laquage.",
    )
