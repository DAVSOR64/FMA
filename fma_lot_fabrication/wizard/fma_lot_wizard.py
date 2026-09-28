# -*- coding: utf-8 -*-
"""Wizard de mise en lot, lance depuis le devis.

Il remonte les lignes du devis et laisse saisir, en face de chacune, le
numero de lot et la quantite a placer dans ce lot. A la validation, les lots
sont crees (ou completes) et les lignes de lot generees.

Une meme ligne de devis peut etre repartie sur plusieurs lots : il suffit de
relancer le wizard, qui ne propose alors que le reste a lotir.
"""
from collections import OrderedDict

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero


class FmaLotWizard(models.TransientModel):
    _name = "fma.lot.wizard"
    _description = "Mise en lot des lignes de devis"

    order_id = fields.Many2one(
        "sale.order",
        string="Commande",
        required=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        related="order_id.company_id",
        string="Societe",
    )
    partner_id = fields.Many2one(
        related="order_id.partner_id",
        string="Client",
    )
    line_ids = fields.One2many(
        "fma.lot.wizard.line",
        "wizard_id",
        string="Lignes",
    )
    max_menuiserie = fields.Integer(
        string="Menuiseries max par lot",
        compute="_compute_max_menuiserie",
    )
    date_planned_start = fields.Datetime(
        string="Date planifiee",
        default=fields.Datetime.now,
        help="Date reprise sur les lots crees par ce wizard.",
    )

    @api.depends("company_id")
    def _compute_max_menuiserie(self):
        for wizard in self:
            wizard.max_menuiserie = (
                wizard.company_id.fma_lot_max_menuiserie or 0
            )

    # ------------------------------------------------------------------
    # Pre-remplissage
    # ------------------------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order_id = res.get("order_id") or self.env.context.get(
            "default_order_id"
        )
        if not order_id or "line_ids" not in fields_list:
            return res
        order = self.env["sale.order"].browse(order_id)
        commands = []
        for line in order.order_line.filtered("is_lotable"):
            if float_is_zero(line.qty_to_lot, precision_digits=2):
                continue
            commands.append(
                Command.create(
                    {
                        "sale_line_id": line.id,
                        "qty_in_lot": line.qty_to_lot,
                    }
                )
            )
        if not commands:
            raise UserError(
                _(
                    "Toutes les lignes de la commande %s sont deja loties.",
                    order.display_name,
                )
            )
        res["line_ids"] = commands
        return res

    # ------------------------------------------------------------------
    # Aide a la saisie
    # ------------------------------------------------------------------
    def action_autofill(self):
        """Propose une repartition en lots de taille maximale.

        Remplit la colonne "N° de lot" en enchainant les menuiseries dans
        l'ordre des lignes, sans depasser le plafond parametre. Les numeros
        sont pris sur la sequence des lots ; ils restent modifiables avant
        validation.
        """
        self.ensure_one()
        maximum = self.max_menuiserie
        if not maximum:
            raise UserError(
                _(
                    "Aucun plafond de menuiseries par lot n'est parametre : "
                    "la repartition automatique ne peut pas s'appliquer.\n"
                    "Renseignez-le dans Fabrication > Configuration > "
                    "Parametres."
                )
            )
        Sequence = self.env["ir.sequence"].with_company(self.company_id.id)
        current_ref = None
        current_qty = 0.0
        for line in self.line_ids.sorted(lambda l: l.sale_line_id.sequence):
            qty = line.qty_in_lot
            if float_is_zero(qty, precision_digits=2):
                continue
            if current_ref is None or current_qty + qty > maximum:
                current_ref = Sequence.next_by_code("fma.lot.fabrication")
                current_qty = 0.0
            line.lot_ref = current_ref
            current_qty += qty
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _get_lot(self, ref, lot_cache):
        """Retourne le lot correspondant a ``ref``, en le creant au besoin."""
        self.ensure_one()
        if ref in lot_cache:
            return lot_cache[ref]
        Lot = self.env["fma.lot.fabrication"]
        lot = Lot.search(
            [
                ("name", "=", ref),
                ("company_id", "=", self.company_id.id),
                ("state", "in", ("draft", "confirmed")),
            ],
            limit=1,
        )
        if not lot:
            lot = Lot.create(
                {
                    "name": ref,
                    "company_id": self.company_id.id,
                    "date_planned_start": self.date_planned_start,
                }
            )
        lot_cache[ref] = lot
        return lot

    def action_apply(self):
        """Cree ou complete les lots a partir de la saisie."""
        self.ensure_one()
        LotLine = self.env["fma.lot.fabrication.line"]
        precision = self.env["decimal.precision"].precision_get(
            "Product Unit of Measure"
        )

        # Regroupement par numero de lot, dans l'ordre de saisie.
        grouped = OrderedDict()
        for line in self.line_ids:
            if float_is_zero(line.qty_in_lot, precision_digits=precision):
                continue
            if line.lot_id:
                key = line.lot_id
            elif line.lot_ref:
                key = line.lot_ref.strip()
            else:
                continue
            if not key:
                continue
            if float_compare(
                line.qty_in_lot, line.qty_to_lot, precision_digits=precision
            ) > 0:
                raise UserError(
                    _(
                        "Ligne %(line)s : vous voulez lotir %(qty)s unites "
                        "mais il n'en reste que %(rest)s a lotir.",
                        line=line.sale_line_id.display_name,
                        qty=line.qty_in_lot,
                        rest=line.qty_to_lot,
                    )
                )
            grouped.setdefault(key, []).append(line)

        if not grouped:
            raise UserError(
                _(
                    "Aucune ligne n'a de numero de lot et de quantite : "
                    "renseignez au moins une ligne."
                )
            )

        lot_cache = {}
        lots = self.env["fma.lot.fabrication"]
        for key, wizard_lines in grouped.items():
            if isinstance(key, str):
                lot = self._get_lot(key, lot_cache)
            else:
                lot = key
                if lot.state not in ("draft", "confirmed"):
                    raise UserError(
                        _(
                            "Le lot %(lot)s est a l'etat %(state)s : il n'est "
                            "plus modifiable.",
                            lot=lot.display_name,
                            state=lot.state,
                        )
                    )
            lots |= lot

            for wline in wizard_lines:
                existing = LotLine.search(
                    [
                        ("lot_id", "=", lot.id),
                        ("sale_line_id", "=", wline.sale_line_id.id),
                    ],
                    limit=1,
                )
                if existing:
                    # Le wizard ne propose que le reste a lotir : une
                    # nouvelle saisie sur le meme couple s'additionne.
                    existing.product_qty += wline.qty_in_lot
                else:
                    LotLine.create(
                        {
                            "lot_id": lot.id,
                            "sale_line_id": wline.sale_line_id.id,
                            "product_qty": wline.qty_in_lot,
                        }
                    )

        for lot in lots:
            lot.message_post(
                body=_(
                    "Lot alimente depuis la commande %s.",
                    self.order_id.display_name,
                )
            )
        self.order_id.message_post(
            body=_(
                "Mise en lot : %s.",
                ", ".join(lots.mapped("name")),
            )
        )

        action = self.env["ir.actions.act_window"]._for_xml_id(
            "fma_lot_fabrication.action_fma_lot_fabrication"
        )
        action["domain"] = [("id", "in", lots.ids)]
        if len(lots) == 1:
            action["views"] = [
                (
                    self.env.ref(
                        "fma_lot_fabrication.view_fma_lot_fabrication_form"
                    ).id,
                    "form",
                )
            ]
            action["res_id"] = lots.id
        return action


class FmaLotWizardLine(models.TransientModel):
    _name = "fma.lot.wizard.line"
    _description = "Ligne du wizard de mise en lot"
    _order = "sequence, id"

    wizard_id = fields.Many2one(
        "fma.lot.wizard",
        string="Wizard",
        required=True,
        ondelete="cascade",
    )
    sale_line_id = fields.Many2one(
        "sale.order.line",
        string="Ligne de devis",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(
        related="sale_line_id.sequence",
        string="Sequence",
        store=True,
    )
    product_id = fields.Many2one(
        related="sale_line_id.product_id",
        string="Menuiserie",
    )
    description = fields.Text(
        # sale.order.line.name est un Text (cf. fma.lot.fabrication.line).
        related="sale_line_id.name",
        string="Designation",
    )
    qty_ordered = fields.Float(
        related="sale_line_id.product_uom_qty",
        string="Qte commandee",
    )
    qty_lot = fields.Float(
        related="sale_line_id.qty_lot",
        string="Deja lotie",
    )
    qty_to_lot = fields.Float(
        related="sale_line_id.qty_to_lot",
        string="Reste a lotir",
    )
    lot_ref = fields.Char(
        string="N° de lot",
        help="Numero du lot dans lequel placer cette quantite. S'il "
        "correspond a un lot existant modifiable, la ligne y est ajoutee ; "
        "sinon le lot est cree.",
    )
    lot_id = fields.Many2one(
        "fma.lot.fabrication",
        string="Lot existant",
        domain="[('state', 'in', ('draft', 'confirmed'))]",
        help="Alternative au numero saisi : rattacher directement la ligne "
        "a un lot deja cree.",
    )
    qty_in_lot = fields.Float(
        string="Qte dans le lot",
        digits="Product Unit of Measure",
        help="Quantite de cette ligne a placer dans le lot indique.",
    )
