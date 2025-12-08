from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = "product.template"

    subfamily_id = fields.Many2one(
        "product.subfamily",
        string="Sous-famille",
        domain="[('product_categ_id', '=', categ_id)]",
        help="Sous-famille dépendante de la catégorie de produit.",
    )
