# -*- coding: utf-8 -*-
"""Point d'entree commercial de la mise en lot.

Le devis est l'ecran d'ou part le lotissement : un bouton ouvre le wizard
qui liste les lignes et laisse saisir, pour chacune, un numero de lot et la
quantite a y placer.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    lot_ids = fields.Many2many(
        "fma.lot.fabrication",
        string="Lots de fabrication",
        compute="_compute_lot_ids",
        store=False,
    )
    lot_count = fields.Integer(
        string="Nb lots",
        compute="_compute_lot_ids",
    )
    qty_to_lot_total = fields.Float(
        string="Reste a lotir",
        compute="_compute_lot_ids",
        digits="Product Unit of Measure",
    )

    @api.depends(
        "order_line.lot_line_ids.lot_id",
        "order_line.lot_line_ids.lot_id.state",
        "order_line.lot_line_ids.product_qty",
        "order_line.product_uom_qty",
        "order_line.is_lotable",
    )
    def _compute_lot_ids(self):
        for order in self:
            lot_lines = order.order_line.lot_line_ids.filtered(
                lambda l: l.lot_id.state != "cancel"
            )
            order.lot_ids = lot_lines.mapped("lot_id")
            order.lot_count = len(order.lot_ids)
            order.qty_to_lot_total = sum(
                order.order_line.filtered("is_lotable").mapped("qty_to_lot")
            )

    def action_open_lot_wizard(self):
        """Ouvre le wizard de mise en lot pour cette commande."""
        self.ensure_one()
        if self.state in ("cancel",):
            raise UserError(
                _("La commande %s est annulee.", self.display_name)
            )
        lines = self.order_line.filtered("is_lotable")
        if not lines:
            raise UserError(
                _(
                    "La commande %s ne contient aucune ligne a lotir "
                    "(articles stockables ou consommables).",
                    self.display_name,
                )
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Mise en lot - %s", self.name),
            "res_model": "fma.lot.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_order_id": self.id},
        }

    def action_view_lots(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "fma_lot_fabrication.action_fma_lot_fabrication"
        )
        lots = self.lot_ids
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
