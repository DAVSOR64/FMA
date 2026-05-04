from odoo import models, fields


class ProductSubSubFamily(models.Model):
    _name = "product.subsubfamily"
    _description = "Sous-sous-famille de produit"
    _order = "family_id, subfamily_id, sequence, name"

    name = fields.Char(string="Sous-sous-famille", required=True)
    code = fields.Char(string="Code")
    family_id = fields.Many2one(
        "product.family",
        string="Famille",
        related="subfamily_id.family_id",
        store=True,
        readonly=True,
    )
    subfamily_id = fields.Many2one(
        "product.subfamily",
        string="Sous-famille",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "product_subsubfamily_subfamily_name_uniq",
            "unique(subfamily_id, name)",
            "Cette sous-sous-famille existe déjà pour cette sous-famille.",
        ),
    ]
