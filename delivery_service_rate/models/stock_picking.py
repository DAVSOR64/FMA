# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    #planned_date_reason = fields.Char(
    #    string="Motif changement date prévue",
    #    copy=False,
    #)
    
    planned_date_reason = fields.Selection(
    [
        ("supplier", "Fournisseur"),
        ("internal", "Cause interne"),
        ("customer", "Client"),
    ],
    string="Motif changement date prévue",
    copy=False,
)
    planned_date_changed = fields.Boolean(
        string="Date prévue modifiée",
        copy=False,
        default=False,
    )
    require_planned_date_reason = fields.Boolean(
        string="Motif requis",
        compute="_compute_require_planned_date_reason",
    )
    is_customer_delivery = fields.Boolean(
        string="Livraison client",
        compute="_compute_is_customer_delivery",
    )

    @api.depends("picking_type_id.code")
    def _compute_is_customer_delivery(self):
        for picking in self:
            picking.is_customer_delivery = picking.picking_type_id.code == "outgoing"

    @api.depends("scheduled_date", "planned_date_changed", "picking_type_id.code")
    def _compute_require_planned_date_reason(self):
        for picking in self:
            origin_scheduled_date = picking._origin.scheduled_date if picking._origin else False
            picking.require_planned_date_reason = bool(
                picking.picking_type_id.code == "outgoing"
                and origin_scheduled_date
                and picking.scheduled_date
                and picking.scheduled_date != origin_scheduled_date
            )

    @api.onchange("scheduled_date")
    def _onchange_scheduled_date_planned_date_reason(self):
        for picking in self:
            if (
                picking.picking_type_id.code == "outgoing"
                and picking._origin
                and picking._origin.scheduled_date
                and picking.scheduled_date
                and picking.scheduled_date != picking._origin.scheduled_date
            ):
                picking.planned_date_changed = True
                picking.require_planned_date_reason = True

    def write(self, vals):
        if "scheduled_date" in vals:
            for picking in self:
                if (
                    picking.picking_type_id.code == "outgoing"
                    and picking.scheduled_date
                    and vals.get("scheduled_date")
                    and str(picking.scheduled_date) != str(vals.get("scheduled_date"))
                ):
                    vals.setdefault("planned_date_changed", True)
        return super().write(vals)
