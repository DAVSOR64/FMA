# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models
from odoo.exceptions import ValidationError

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    cpt = 0
    def _check_outstandings(self):
        for order in self:
            if order.partner_id.outstandings > order.partner_id.x_studio_allianz_couverture_euleur:
                cpt = 1
                #raise ValidationError(
                 #   "The partner %s has outstanding credits (%s) that exceed their allowed coverage (%s)." % (
                  #      order.partner_id.name,
                  #      order.partner_id.outstandings,
                  #      order.partner_id.x_studio_allianz_couverture_euleur
                  #  )
                #)

    def action_validation(self):
        self._check_outstandings()
        return super(SaleOrder, self).action_validation()

    def action_confirm(self):
        self._check_outstandings()
        return super(SaleOrder, self).action_confirm()
