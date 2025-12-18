from odoo import models, fields, api


class SaleDelayReason(models.Model):
    _name = "sale.delay.reason"
    _description = "Motif de retard (N1/N2)"
    _order = "level1, level2"

    level1 = fields.Char(string="Motif niveau 1", required=True)
    level2 = fields.Char(string="Motif niveau 2")
    active = fields.Boolean(default=True)

    name = fields.Char(string="Nom", compute="_compute_name", store=True)

    @api.depends("level1", "level2")
    def _compute_name(self):
        for rec in self:
            rec.name = f"{rec.level1} / {rec.level2}" if rec.level2 else (rec.level1 or "")
