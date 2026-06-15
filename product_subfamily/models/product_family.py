from odoo import models, fields


class ProductFamily(models.Model):
    _name = "product.family"
    _description = "Famille de produit"
    _order = "sequence, name"

    name = fields.Char(string="Famille", required=True)
    code = fields.Char(string="Code")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _product_family_name_uniq = models.Constraint(
        'unique(name)',
        'Cette famille existe déjà.',
    )
