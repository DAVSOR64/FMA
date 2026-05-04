from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ProductFamilyTriplet(models.Model):
    _name = "product.family.triplet"
    _description = "Correspondance famille / sous-famille / sous-sous-famille"
    _order = "family_id, subfamily_id, subsubfamily_id"
    _rec_name = "display_name"

    display_name = fields.Char(compute="_compute_display_name", store=True)
    family_id = fields.Many2one(
        "product.family",
        string="Famille",
        required=True,
        ondelete="cascade",
    )
    subfamily_id = fields.Many2one(
        "product.subfamily",
        string="Sous-famille",
        required=True,
        domain="[('family_id', '=', family_id)]",
        ondelete="cascade",
    )
    subsubfamily_id = fields.Many2one(
        "product.subsubfamily",
        string="Sous-sous-famille",
        required=True,
        domain="[('subfamily_id', '=', subfamily_id)]",
        ondelete="cascade",
    )
    analytic_account_sale_id = fields.Many2one(
        "account.analytic.account",
        string="Compte analytique vente",
        required=True,
    )
    analytic_account_purchase_id = fields.Many2one(
        "account.analytic.account",
        string="Compte analytique achat",
        required=True,
    )
    categ_id = fields.Many2one(
        "product.category",
        string="Catégorie Odoo générée",
        readonly=True,
        copy=False,
        help="Catégorie créée automatiquement sous All / Famille / Sous-famille / Sous-sous-famille.",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "product_family_triplet_uniq",
            "unique(family_id, subfamily_id, subsubfamily_id)",
            "Ce triplet famille / sous-famille / sous-sous-famille existe déjà.",
        ),
    ]

    @api.depends("family_id", "subfamily_id", "subsubfamily_id")
    def _compute_display_name(self):
        for rec in self:
            parts = [rec.family_id.name, rec.subfamily_id.name, rec.subsubfamily_id.name]
            rec.display_name = " / ".join([p for p in parts if p])

    @api.constrains("family_id", "subfamily_id", "subsubfamily_id")
    def _check_hierarchy_consistency(self):
        for rec in self:
            if rec.subfamily_id and rec.subfamily_id.family_id != rec.family_id:
                raise ValidationError(_("La sous-famille sélectionnée n'appartient pas à la famille."))
            if rec.subsubfamily_id and rec.subsubfamily_id.subfamily_id != rec.subfamily_id:
                raise ValidationError(_("La sous-sous-famille sélectionnée n'appartient pas à la sous-famille."))

    def _get_root_category(self):
        root = self.env.ref("product.product_category_all", raise_if_not_found=False)
        if root:
            return root
        return self.env["product.category"].search([("parent_id", "=", False)], limit=1)

    def _get_or_create_category(self, name, parent):
        Category = self.env["product.category"]
        category = Category.search([
            ("name", "=", name),
            ("parent_id", "=", parent.id if parent else False),
        ], limit=1)
        if not category:
            category = Category.create({
                "name": name,
                "parent_id": parent.id if parent else False,
            })
        return category

    def _prepare_generated_category_values(self):
        self.ensure_one()
        vals = {
            "analytic_account_sale_id": self.analytic_account_sale_id.id,
            "analytic_account_purchase_id": self.analytic_account_purchase_id.id,
        }
        if "property_cost_method" in self.env["product.category"]._fields:
            vals["property_cost_method"] = "average"
        return vals

    def _ensure_generated_category(self):
        for rec in self:
            if not (rec.family_id and rec.subfamily_id and rec.subsubfamily_id):
                continue

            root = rec._get_root_category()
            family_category = rec._get_or_create_category(rec.family_id.name, root)
            subfamily_category = rec._get_or_create_category(rec.subfamily_id.name, family_category)
            subsubfamily_category = rec._get_or_create_category(rec.subsubfamily_id.name, subfamily_category)

            subsubfamily_category.write(rec._prepare_generated_category_values())
            rec.categ_id = subsubfamily_category.id

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ensure_generated_category()
        return records

    def write(self, vals):
        res = super().write(vals)
        if {
            "family_id",
            "subfamily_id",
            "subsubfamily_id",
            "analytic_account_sale_id",
            "analytic_account_purchase_id",
        } & set(vals):
            self._ensure_generated_category()
            products = self.env["product.template"].search([
                ("family_id", "in", self.mapped("family_id").ids),
                ("subfamily_id", "in", self.mapped("subfamily_id").ids),
                ("subsubfamily_id", "in", self.mapped("subsubfamily_id").ids),
            ])
            products._apply_family_triplet_category()
        return res
