# -*- coding: utf-8 -*-
from odoo import models, fields, api


class StockPicking(models.Model):
    _inherit = "stock.picking"

    so_retard_motif_level1_id = fields.Many2one(
        "sale.delay.reason",
        string="Motif retard - Niveau 1",
        domain="[('level','=','1'), ('active','=',True)]",
    )

    so_retard_motif_level2_id = fields.Many2one(
        "sale.delay.reason",
        string="Motif retard - Niveau 2",
        domain="[('level','=','2'), ('active','=',True), ('parent_id','=',so_retard_motif_level1_id)]",
    )

    @api.onchange("so_retard_motif_level1_id")
    def _onchange_so_retard_motif_level1_id(self):
        """Quand on change le N1, on vide le N2 pour éviter incohérence."""
        for rec in self:
            rec.so_retard_motif_level2_id = False
