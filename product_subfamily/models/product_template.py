from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    family_id = fields.Many2one(
        "product.family",
        string="Famille",
        tracking=True,
    )
    subfamily_id = fields.Many2one(
        "product.subfamily",
        string="Sous-famille",
        domain="[('family_id', '=', family_id)]",
        tracking=True,
    )
    subsubfamily_id = fields.Many2one(
        "product.subsubfamily",
        string="Sous-sous-famille",
        domain="[('subfamily_id', '=', subfamily_id)]",
        tracking=True,
    )

    @api.onchange("family_id")
    def _onchange_family_id(self):
        for product in self:
            if product.subfamily_id and product.subfamily_id.family_id != product.family_id:
                product.subfamily_id = False
                product.subsubfamily_id = False
            product._apply_family_triplet_category()

    @api.onchange("subfamily_id")
    def _onchange_subfamily_id(self):
        for product in self:
            if product.subfamily_id:
                product.family_id = product.subfamily_id.family_id
            if product.subsubfamily_id and product.subsubfamily_id.subfamily_id != product.subfamily_id:
                product.subsubfamily_id = False
            product._apply_family_triplet_category()

    @api.onchange("subsubfamily_id")
    def _onchange_subsubfamily_id(self):
        for product in self:
            if product.subsubfamily_id:
                product.subfamily_id = product.subsubfamily_id.subfamily_id
                product.family_id = product.subsubfamily_id.family_id
            product._apply_family_triplet_category()

    def _find_family_triplet(self):
        self.ensure_one()
        if not (self.family_id and self.subfamily_id and self.subsubfamily_id):
            return self.env["product.family.triplet"]
        return self.env["product.family.triplet"].search([
            ("family_id", "=", self.family_id.id),
            ("subfamily_id", "=", self.subfamily_id.id),
            ("subsubfamily_id", "=", self.subsubfamily_id.id),
            ("active", "=", True),
        ], limit=1)

    def _apply_family_triplet_category(self):
        for product in self:
            triplet = product._find_family_triplet()
            if triplet:
                product.categ_id = triplet.categ_id

    @api.constrains("family_id", "subfamily_id", "subsubfamily_id")
    def _check_family_triplet_exists(self):
        for product in self:
            if product.family_id or product.subfamily_id or product.subsubfamily_id:
                if not (product.family_id and product.subfamily_id and product.subsubfamily_id):
                    raise ValidationError(_("Veuillez renseigner Famille, Sous-famille et Sous-sous-famille."))
                triplet = product._find_family_triplet()
                if not triplet:
                    raise ValidationError(_("Aucun triplet actif n'est configuré pour cette sélection."))

    @api.model_create_multi
    def create(self, vals_list):
        products = super().create(vals_list)
        products._apply_family_triplet_category()
        return products

    def write(self, vals):
        res = super().write(vals)
        if {"family_id", "subfamily_id", "subsubfamily_id"} & set(vals):
            self._apply_family_triplet_category()
        return res
