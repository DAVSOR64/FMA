# -*- coding: utf-8 -*-
"""Rattachement des ordres de fabrication a leur lot.

Les OF d'un meme lot sont relies par ``lot_fabrication_id`` (la reference de
lot) et non par le chainage parent/enfant natif : c'est ce qui permet de
regrouper 1 OF Debit + N OF Assemblage dans une seule vue, quel que soit le
mode de reapprovisionnement.
"""
import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    lot_fabrication_id = fields.Many2one(
        "fma.lot.fabrication",
        string="Lot de fabrication",
        copy=False,
        index=True,
        ondelete="set null",
        help="Lot regroupant cet OF avec les autres OF de la meme serie.",
    )
    lot_production_type = fields.Selection(
        [
            ("debit", "Debit"),
            ("assemblage", "Assemblage"),
        ],
        string="Type dans le lot",
        copy=False,
        index=True,
        help="Debit : 1 par lot, consomme les profiles. "
        "Assemblage : 1 par menuiserie, point de declaration de fabrication.",
    )
    lot_line_id = fields.Many2one(
        "fma.lot.fabrication.line",
        string="Ligne de lot",
        copy=False,
        ondelete="set null",
    )
    lot_sale_line_id = fields.Many2one(
        "sale.order.line",
        string="Ligne de commande",
        copy=False,
        index=True,
        ondelete="set null",
    )
    lot_sale_order_id = fields.Many2one(
        related="lot_sale_line_id.order_id",
        string="Commande liee",
        store=True,
    )

    # ------------------------------------------------------------------
    # Composants ajoutes hors nomenclature
    # ------------------------------------------------------------------
    def _lot_move_vals(self, product, qty, uom=None):
        """Valeurs d'un composant ajoute hors nomenclature.

        On delegue a ``_get_move_raw_values``, la methode native qui construit
        les composants d'un OF : elle gere l'emplacement de production, la
        methode d'approvisionnement, l'entrepot et les dates, et elle suit les
        renommages de champs de ``stock.move`` d'une version a l'autre.
        """
        self.ensure_one()
        vals = self._get_move_raw_values(product, qty, uom or product.uom_id)
        if self.origin:
            vals["origin"] = self.origin
        return vals

    def _add_debit_component(self, product_debit, qty):
        """Ajoute l'ensemble debite du lot aux composants de l'OF assemblage.

        C'est le lien matiere entre l'OF Debit (qui produit l'ensemble) et
        l'OF Assemblage (qui le consomme).
        """
        self.ensure_one()
        if not product_debit or not qty:
            return self.env["stock.move"]
        already = self.move_raw_ids.filtered(
            lambda m: m.product_id == product_debit
        )
        if already:
            return already
        return self.env["stock.move"].create(
            self._lot_move_vals(product_debit, qty)
        )

    def _add_lot_material_moves(self, material_lines):
        """Alimente les composants de l'OF Debit depuis le besoin matiere."""
        self.ensure_one()
        Move = self.env["stock.move"]
        moves = Move.browse()
        existing = self.move_raw_ids.mapped("product_id")
        for line in material_lines:
            if line.product_id in existing:
                continue
            moves |= Move.create(
                self._lot_move_vals(
                    line.product_id, line.product_qty, line.product_uom_id
                )
            )
        return moves

    # ------------------------------------------------------------------
    # Propagation d'etat vers le lot
    # ------------------------------------------------------------------
    def write(self, vals):
        res = super().write(vals)
        if "state" in vals:
            lots = self.mapped("lot_fabrication_id")
            if lots:
                lots._check_production_done()
        return res

    def action_view_lot_fabrication(self):
        self.ensure_one()
        if not self.lot_fabrication_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "name": _("Lot de fabrication"),
            "res_model": "fma.lot.fabrication",
            "res_id": self.lot_fabrication_id.id,
            "view_mode": "form",
        }
