from odoo import models, fields, api


class StockPicking(models.Model):
    _inherit = "stock.picking"

    so_retard_motif_level1_id = fields.Many2one(
        "sale.delay.category",
        string="Motif",
    )

    so_retard_motif_level2_id = fields.Many2one(
        "sale.delay.reason",
        string="Désignation",
        domain="[('category_id', '=', so_retard_motif_level1_id)]",
    )

    @api.onchange("so_retard_motif_level1_id")
    def _onchange_so_retard_motif_level1_id(self):
        # Si on change le Motif (catégorie), on reset la Désignation
        self.so_retard_motif_level2_id = False
