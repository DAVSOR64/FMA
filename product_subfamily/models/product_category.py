from odoo import models, fields


class ProductCategory(models.Model):
    _inherit = "product.category"

    analytic_account_sale_id = fields.Many2one(
        "account.analytic.account",
        string="Compte analytique vente",
        company_dependent=True,
    )
    analytic_account_purchase_id = fields.Many2one(
        "account.analytic.account",
        string="Compte analytique achat",
        company_dependent=True,
    )
