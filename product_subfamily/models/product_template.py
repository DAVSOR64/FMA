from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    subfamily_id = fields.Many2one(
        'product.subfamily',
        string="Sous catégorie",
        domain="[('product_categ_id', '=', categ_id)]",
        help="Sous catégorie dépendante de la catégorie de produit.",
    )
