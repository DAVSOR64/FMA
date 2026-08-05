# -*- coding: utf-8 -*-
"""Lot de fabrication FMA.

Un lot regroupe des lignes de devis (= des menuiseries) pour la production.
Il porte deux niveaux d'ordres de fabrication :

* 1 OF Debit  -> niveau lot, consomme les profiles, porte l'optimisation de
  coupe et sert de point d'entree aux approvisionnements ;
* N OF Assemblage -> 1 par menuiserie, c'est la que l'on declare la
  fabrication ligne par ligne.

Les deux niveaux sont relies par ``lot_fabrication_id`` (la reference de lot),
et non par le chainage parent/enfant natif d'Odoo.
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero

_logger = logging.getLogger(__name__)


def uom_fname(model):
    """Nom du champ UoM sur ``model``.

    Odoo a renomme ``product_uom`` en ``product_uom_id`` a des versions
    differentes selon les modeles ; on resout le nom au runtime plutot que de
    le figer, pour rester compatible entre versions.
    """
    if "product_uom_id" in model._fields:
        return "product_uom_id"
    return "product_uom"


def date_start_fname(model):
    """Nom du champ de date de debut planifiee sur mrp.production."""
    if "date_start" in model._fields:
        return "date_start"
    return "date_planned_start"


class FmaLotFabrication(models.Model):
    _name = "fma.lot.fabrication"
    _description = "Lot de fabrication"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_planned_start desc, name desc"

    name = fields.Char(
        string="Numero de lot",
        required=True,
        copy=False,
        readonly=False,
        default="/",
        tracking=True,
        index=True,
    )
    state = fields.Selection(
        [
            ("draft", "Brouillon"),
            ("confirmed", "Confirme"),
            ("progress", "En production"),
            ("done", "Termine"),
            ("cancel", "Annule"),
        ],
        string="Etat",
        default="draft",
        required=True,
        copy=False,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Societe",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Client",
        compute="_compute_partner_id",
        store=True,
        tracking=True,
        help="Client du (ou du premier) devis loti. Un lot peut couvrir "
        "plusieurs commandes d'un meme chantier.",
    )
    date_planned_start = fields.Datetime(
        string="Date planifiee",
        default=fields.Datetime.now,
        tracking=True,
        help="Date reprise sur les OF generes.",
    )

    # --- Composition du lot -------------------------------------------------
    line_ids = fields.One2many(
        "fma.lot.fabrication.line",
        "lot_id",
        string="Menuiseries du lot",
        copy=True,
    )
    material_line_ids = fields.One2many(
        "fma.lot.material.line",
        "lot_id",
        string="Besoin matiere",
        copy=True,
        help="Besoin matiere du lot (profiles, renforts...). Utilise comme "
        "composants de l'OF Debit lorsque l'article debite n'a pas de "
        "nomenclature dediee.",
    )
    menuiserie_qty = fields.Float(
        string="Menuiseries",
        compute="_compute_menuiserie_qty",
        store=True,
        help="Nombre total de menuiseries du lot (somme des quantites lotees).",
    )
    max_menuiserie = fields.Integer(
        string="Maximum par lot",
        compute="_compute_max_menuiserie",
        help="Plafond parametre au niveau de la societe.",
    )
    sale_order_ids = fields.Many2many(
        "sale.order",
        string="Commandes",
        compute="_compute_sale_order_ids",
        store=False,
    )
    sale_order_count = fields.Integer(
        string="Nb commandes",
        compute="_compute_sale_order_ids",
    )

    # --- Production ---------------------------------------------------------
    product_debit_id = fields.Many2one(
        "product.product",
        string="Article debite",
        domain="[('type', 'in', ('consu', 'product'))]",
        tracking=True,
        help="Article intermediaire produit par l'OF Debit et consomme par "
        "chaque OF Assemblage. Par defaut, l'article parametre sur la societe.",
    )
    production_ids = fields.One2many(
        "mrp.production",
        "lot_fabrication_id",
        string="Ordres de fabrication",
    )
    production_debit_id = fields.Many2one(
        "mrp.production",
        string="OF Debit",
        copy=False,
        readonly=True,
    )
    production_assembly_ids = fields.One2many(
        "mrp.production",
        "lot_fabrication_id",
        string="OF Assemblage",
        domain=[("lot_production_type", "=", "assemblage")],
    )
    production_count = fields.Integer(
        string="Nb OF",
        compute="_compute_production_count",
    )
    procurement_group_id = fields.Many2one(
        "procurement.group",
        string="Groupe d'approvisionnement",
        copy=False,
        readonly=True,
        help="Groupe utilise pour rattacher les achats du lot.",
    )
    purchase_ids = fields.One2many(
        "purchase.order",
        "lot_fabrication_id",
        string="Achats du lot",
    )
    purchase_count = fields.Integer(
        string="Nb achats",
        compute="_compute_purchase_count",
    )

    # --- Divers -------------------------------------------------------------
    logikal_ref = fields.Char(
        string="Reference LOGIKAL",
        tracking=True,
        help="Reference du lot / de l'optimisation cote LOGIKAL, pour "
        "rapprochement.",
    )
    note = fields.Html(string="Notes")

    _name_company_uniq = models.Constraint(
        "unique(name, company_id)",
        "Le numéro de lot doit être unique par société.",
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends("line_ids.product_qty")
    def _compute_menuiserie_qty(self):
        for lot in self:
            lot.menuiserie_qty = sum(lot.line_ids.mapped("product_qty"))

    @api.depends("company_id")
    def _compute_max_menuiserie(self):
        for lot in self:
            lot.max_menuiserie = lot.company_id.fma_lot_max_menuiserie or 0

    @api.depends("line_ids.order_id")
    def _compute_sale_order_ids(self):
        for lot in self:
            orders = lot.line_ids.mapped("order_id")
            lot.sale_order_ids = orders
            lot.sale_order_count = len(orders)

    @api.depends("line_ids.order_id")
    def _compute_partner_id(self):
        for lot in self:
            orders = lot.line_ids.mapped("order_id")
            lot.partner_id = orders[:1].partner_id

    @api.depends("production_ids")
    def _compute_production_count(self):
        for lot in self:
            lot.production_count = len(lot.production_ids)

    @api.depends("purchase_ids")
    def _compute_purchase_count(self):
        for lot in self:
            lot.purchase_count = len(lot.purchase_ids)

    # ------------------------------------------------------------------
    # Contraintes
    # ------------------------------------------------------------------
    @api.constrains("line_ids", "company_id")
    def _check_max_menuiserie(self):
        for lot in self:
            maximum = lot.company_id.fma_lot_max_menuiserie
            if not maximum:
                continue
            total = sum(lot.line_ids.mapped("product_qty"))
            if float_compare(total, maximum, precision_digits=2) > 0:
                raise ValidationError(
                    _(
                        "Le lot %(lot)s contient %(qty)s menuiseries, or le "
                        "maximum autorise est de %(max)s.\n"
                        "Ce plafond est parametrable dans Fabrication > "
                        "Configuration > Parametres.",
                        lot=lot.name,
                        qty=total,
                        max=maximum,
                    )
                )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "/":
                company_id = vals.get("company_id") or self.env.company.id
                vals["name"] = self.env["ir.sequence"].with_company(
                    company_id
                ).next_by_code("fma.lot.fabrication") or _("Nouveau lot")
        return super().create(vals_list)

    def copy_data(self, default=None):
        default = dict(default or {})
        default.setdefault("name", "/")
        default.setdefault("state", "draft")
        return super().copy_data(default)

    def unlink(self):
        for lot in self:
            if lot.production_ids:
                raise UserError(
                    _(
                        "Impossible de supprimer le lot %s : des ordres de "
                        "fabrication lui sont rattaches. Annulez-le plutot.",
                        lot.name,
                    )
                )
        return super().unlink()

    # ------------------------------------------------------------------
    # Transitions d'etat
    # ------------------------------------------------------------------
    def action_confirm(self):
        for lot in self:
            if lot.state != "draft":
                continue
            if not lot.line_ids:
                raise UserError(
                    _("Le lot %s ne contient aucune menuiserie.", lot.name)
                )
            lot.state = "confirmed"
        return True

    def action_draft(self):
        for lot in self:
            if lot.production_ids.filtered(lambda p: p.state != "cancel"):
                raise UserError(
                    _(
                        "Le lot %s a des OF actifs : annulez-les avant de "
                        "repasser le lot en brouillon.",
                        lot.name,
                    )
                )
            lot.state = "draft"
        return True

    def action_cancel(self):
        for lot in self:
            productions = lot.production_ids.filtered(
                lambda p: p.state not in ("done", "cancel")
            )
            if productions:
                productions.action_cancel()
            lot.state = "cancel"
        return True

    def _check_production_done(self):
        """Bascule le lot en ``done`` quand tous ses OF sont termines."""
        for lot in self:
            if lot.state not in ("progress", "confirmed"):
                continue
            productions = lot.production_ids.filtered(
                lambda p: p.state != "cancel"
            )
            if productions and all(p.state == "done" for p in productions):
                lot.state = "done"

    # ------------------------------------------------------------------
    # Generation des ordres de fabrication
    # ------------------------------------------------------------------
    def action_generate_orders(self):
        """Genere 1 OF Debit + N OF Assemblage pour chaque lot.

        Idempotent : les OF deja generes (et non annules) ne sont pas
        recrees, ce qui permet de relancer le bouton apres avoir ajoute une
        menuiserie au lot.
        """
        for lot in self:
            if lot.state == "cancel":
                raise UserError(
                    _("Le lot %s est annule.", lot.name)
                )
            if not lot.line_ids:
                raise UserError(
                    _("Le lot %s ne contient aucune menuiserie.", lot.name)
                )
            if lot.state == "draft":
                lot.action_confirm()

            lot._ensure_procurement_group()
            lot._generate_debit_order()
            lot._generate_assembly_orders()

            if lot.state == "confirmed":
                lot.state = "progress"
        return True

    def _ensure_procurement_group(self):
        self.ensure_one()
        if self.procurement_group_id:
            return self.procurement_group_id
        group = self.env["procurement.group"].create(
            {
                "name": self.name,
                "partner_id": self.partner_id.id or False,
            }
        )
        self.procurement_group_id = group
        return group

    def _get_product_debit(self):
        """Article intermediaire produit par l'OF Debit."""
        self.ensure_one()
        if self.product_debit_id:
            return self.product_debit_id
        product = self.company_id.fma_lot_product_debit_id
        if not product:
            product = self.env.ref(
                "fma_lot_fabrication.product_ensemble_debite",
                raise_if_not_found=False,
            )
        if not product:
            raise UserError(
                _(
                    "Aucun article debite n'est parametre.\n"
                    "Renseignez-le sur le lot, ou dans Fabrication > "
                    "Configuration > Parametres > Lots de fabrication."
                )
            )
        self.product_debit_id = product
        return product

    def _get_picking_type(self):
        self.ensure_one()
        picking_type = self.env["stock.picking.type"].search(
            [
                ("code", "=", "mrp_operation"),
                ("company_id", "in", (self.company_id.id, False)),
            ],
            limit=1,
        )
        if not picking_type:
            raise UserError(
                _(
                    "Aucun type d'operation de fabrication n'est configure "
                    "pour la societe %s.",
                    self.company_id.display_name,
                )
            )
        return picking_type

    def _common_production_vals(self, picking_type):
        self.ensure_one()
        Production = self.env["mrp.production"]
        vals = {
            "company_id": self.company_id.id,
            "picking_type_id": picking_type.id,
            "origin": self.name,
            "lot_fabrication_id": self.id,
        }
        if self.date_planned_start:
            vals[date_start_fname(Production)] = self.date_planned_start
        group_fname = self._production_group_fname()
        if group_fname and self.procurement_group_id:
            vals[group_fname] = self.procurement_group_id.id
        return vals

    @api.model
    def _production_group_fname(self):
        """Champ reliant un OF a son groupe d'approvisionnement.

        Renomme entre versions (``procurement_group_id`` jusqu'en 18,
        ``production_group_id`` en 19) : on resout au runtime et on ne
        renvoie le champ que s'il pointe bien vers ``procurement.group``.
        """
        fields_ = self.env["mrp.production"]._fields
        for fname in ("procurement_group_id", "production_group_id"):
            field = fields_.get(fname)
            if field and field.comodel_name == "procurement.group":
                return fname
        return None

    def _generate_debit_order(self):
        """Cree l'OF de debit du lot (1 par lot)."""
        self.ensure_one()
        if self.production_debit_id and self.production_debit_id.state != "cancel":
            return self.production_debit_id

        Production = self.env["mrp.production"]
        product = self._get_product_debit()
        picking_type = self._get_picking_type()
        qty = self.menuiserie_qty or 1.0

        bom = self.env["mrp.bom"]._bom_find(
            product, company_id=self.company_id.id, bom_type="normal"
        ).get(product)

        vals = self._common_production_vals(picking_type)
        vals.update(
            {
                "product_id": product.id,
                "product_qty": qty,
                uom_fname(Production): product.uom_id.id,
                "bom_id": bom.id if bom else False,
                "lot_production_type": "debit",
            }
        )
        production = Production.create(vals)
        if not bom:
            production._add_lot_material_moves(self.material_line_ids)

        self.production_debit_id = production
        self.message_post(
            body=_("OF de debit %s genere.", production.display_name)
        )
        return production

    def _generate_assembly_orders(self):
        """Cree un OF d'assemblage par ligne de lot non encore servie."""
        self.ensure_one()
        Production = self.env["mrp.production"]
        picking_type = self._get_picking_type()
        product_debit = self._get_product_debit()
        created = Production.browse()

        for line in self.line_ids:
            if line.production_id and line.production_id.state != "cancel":
                continue
            if float_is_zero(line.product_qty, precision_digits=2):
                continue

            product = line.product_id
            if not product:
                continue

            bom = self.env["mrp.bom"]._bom_find(
                product, company_id=self.company_id.id, bom_type="normal"
            ).get(product)

            vals = self._common_production_vals(picking_type)
            vals.update(
                {
                    "product_id": product.id,
                    "product_qty": line.product_qty,
                    uom_fname(Production): (
                        line.sale_line_id.product_uom_id.id or product.uom_id.id
                    ),
                    "bom_id": bom.id if bom else False,
                    "lot_production_type": "assemblage",
                    "lot_line_id": line.id,
                    "lot_sale_line_id": line.sale_line_id.id,
                    "origin": "%s - %s" % (self.name, line.order_id.name or ""),
                }
            )
            production = Production.create(vals)
            production._add_debit_component(product_debit, line.product_qty)
            line.production_id = production
            created |= production

        if created:
            self.message_post(
                body=_(
                    "%(count)s OF d'assemblage generes : %(names)s",
                    count=len(created),
                    names=", ".join(created.mapped("name")),
                )
            )
        return created

    # ------------------------------------------------------------------
    # Actions de navigation
    # ------------------------------------------------------------------
    def action_view_productions(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "mrp.mrp_production_action"
        )
        productions = self.production_ids
        action["domain"] = [("id", "in", productions.ids)]
        action["context"] = {
            "default_lot_fabrication_id": self.id,
            "search_default_lot_fabrication_id": self.id,
        }
        if len(productions) == 1:
            action["views"] = [
                (self.env.ref("mrp.mrp_production_form_view").id, "form")
            ]
            action["res_id"] = productions.id
        return action

    def action_view_purchases(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "purchase.purchase_rfq"
        )
        action["domain"] = [("lot_fabrication_id", "=", self.id)]
        action["context"] = {"default_lot_fabrication_id": self.id}
        return action

    def action_view_sale_orders(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sale.action_orders"
        )
        orders = self.sale_order_ids
        action["domain"] = [("id", "in", orders.ids)]
        if len(orders) == 1:
            action["views"] = [
                (self.env.ref("sale.view_order_form").id, "form")
            ]
            action["res_id"] = orders.id
        return action
