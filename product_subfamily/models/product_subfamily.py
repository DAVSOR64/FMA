from odoo import models, fields


class ProductSubFamily(models.Model):
    _name = 'product.subfamily'
    _description = 'Sous catégorie de produit'
    _order = 'product_categ_id, name'

    name = fields.Char(string="Nom", required=True)
    product_categ_id = fields.Many2one(
        'product.category',
        string="Catégorie de produit",
        required=True,
        help="Catégorie de produit à laquelle cette sous-famille est rattachée.",
    )
    code = fields.Char(string="Code", help="Code interne optionnel.")
    active = fields.Boolean(default=True)
