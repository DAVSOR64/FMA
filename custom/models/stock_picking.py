from odoo import models, fields, api


class StockPicking(models.Model):
    _inherit = "stock.picking"

    so_retard_motif_level1_id = fields.Many2one(
        "sale.delay.reason",
        string="Motif retard (N1)",
        domain="[('level2', '=', False), ('active', '=', True)]",
    )

    so_retard_motif_level2_id = fields.Many2one(
        "sale.delay.reason",
        string="Motif retard (N2)",
        domain="[('level2', '!=', False), ('active', '=', True)]",
    )

    @api.onchange("so_retard_motif_level1_id")
    def _onchange_so_retard_motif_level1_id(self):
        # si on change N1, on vide N2
        self.so_retard_motif_level2_id = False
