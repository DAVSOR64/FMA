from odoo import models, fields


class SaleDelayCategory(models.Model):
    _name = "sale.delay.category"
    _description = "Motif de retard (Catégorie)"
    _order = "name"

    name = fields.Char(string="Motif", required=True)
    active = fields.Boolean(default=True)


class SaleDelayReason(models.Model):
    _name = "sale.delay.reason"
    _description = "Motif de retard (Désignation)"
    _order = "category_id, name"

    name = fields.Char(string="Désignation", required=True)

    category_id = fields.Many2one(
        "sale.delay.category",
        string="Motif",
        required=True,
        ondelete="restrict",
    )

    active = fields.Boolean(default=True)
