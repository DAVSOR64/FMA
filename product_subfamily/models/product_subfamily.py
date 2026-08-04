from odoo import models, fields


class ProductSubFamily(models.Model):
    _name = "product.subfamily"
    _description = "Sous-famille de produit"
    _order = "family_id, sequence, name"

    name = fields.Char(string="Sous-famille", required=True)
    code = fields.Char(string="Code")
    family_id = fields.Many2one(
        "product.family",
        string="Famille",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "product_subfamily_family_name_uniq",
            "unique(family_id, name)",
            "Cette sous-famille existe déjà pour cette famille.",
        ),
    ]
