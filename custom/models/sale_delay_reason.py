from odoo import models, fields, api


class SaleDelayReason(models.Model):
    _name = "sale.delay.reason"
    _description = "Motif de retard (N1/N2)"
    _order = "level, name"

    name = fields.Char(string="Nom", required=True)
    level = fields.Selection(
        [("1", "Niveau 1"), ("2", "Niveau 2")],
        string="Niveau",
        required=True,
        default="1",
    )
    parent_id = fields.Many2one(
        "sale.delay.reason",
        string="Parent (Niveau 1)",
        domain=[("level", "=", "1")],
        ondelete="restrict",
    )
    active = fields.Boolean(default=True)

    @api.constrains("level", "parent_id")
    def _check_parent_level(self):
        for rec in self:
            if rec.level == "2" and not rec.parent_id:
                # niveau 2 doit avoir un parent
                raise ValueError("Un motif de niveau 2 doit avoir un parent (niveau 1).")
            if rec.level == "1" and rec.parent_id:
                # niveau 1 ne doit pas avoir de parent
                rec.parent_id = False
