import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)

class PickingPaletteLine(models.Model):
    _name = 'picking.palette.line'
    _description = 'Ligne de Palette'
    _inherit = ['mail.thread']  # Permet le suivi des modifications dans le fil de discussion Odoo
    _log_access = True  # Active l'historique des accès

    picking_id = fields.Many2one('stock.picking', string="Palette", ondelete='cascade')
    qty = fields.Integer(string="Quantité", track_visibility='onchange')
    length = fields.Float(string="Longueur (mm)", track_visibility='onchange')
    depth = fields.Float(string="Profondeur (mm)", track_visibility='onchange')
    height = fields.Float(string="Hauteur (mm)", track_visibility='onchange')

    @api.model
    def create(self, vals):
        """Suivi des créations dans le fil de discussion Odoo"""
        res = super(PickingPaletteLine, self).create(vals)
        message = "Ligne de palette créée : %s palettes ajoutées." % res.qty
        res.picking_id.message_post(body=message)
        return res

    def write(self, vals):
        """Suivi des modifications dans le fil de discussion Odoo"""
        _logger.warning("********** Fonction write appelée dans PickingPaletteLine *********")  # Log d'avertissement
        res = super(PickingPaletteLine, self).write(vals)
        message = "Ligne de palette mise à jour."
        self.picking_id.message_post(body=message)
        return res
