# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

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
    delivered_on_time = fields.Boolean(
        string="Delivered On Time",
        compute="_compute_delivered_on_time",
        store=True,
        readonly=True,
        copy=False,
    )
    require_planned_date_reason = fields.Boolean(
        string="Motif requis",
        compute="_compute_require_planned_date_reason",
    )
    is_customer_delivery = fields.Boolean(
        string="Livraison client",
        compute="_compute_is_customer_delivery",
    )

    @api.depends("move_ids", "origin")
    def _compute_sale_id(self):
        SaleOrder = self.env["sale.order"]
        for picking in self:
            sale = False
            if picking.origin:
                sale = SaleOrder.search([("name", "=", picking.origin)], limit=1)
            if not sale and picking.move_ids:
                try:
                    sale_lines = picking.move_ids.mapped("sale_line_id")
                    if sale_lines:
                        sale = sale_lines.mapped("order_id")[:1]
                except Exception:
                    pass
            picking.sale_id = sale.id if sale else False

    @api.depends("date_done", "state", "sale_id")
    def _compute_delivered_on_time(self):
        CANDIDATE_FIELDS = ("so_date_de_livraison", "commitment_date")
        for picking in self:
            on_time = False
            if picking.state == "done" and picking.date_done and picking.sale_id:
                dd = fields.Datetime.context_timestamp(
                    picking, picking.date_done
                ).date()
                sd = None
                so = picking.sale_id
                for fname in CANDIDATE_FIELDS:
                    if fname in so._fields:
                        val = getattr(so, fname)
                        if val:
                            sd = val
                            break
                if sd:
                    if isinstance(sd, str):
                        sd = fields.Date.to_date(sd)
                    elif hasattr(sd, "date"):
                        try:
                            sd = sd.date()
                        except Exception:
                            pass
                    dy, dw, _ = dd.isocalendar()
                    sy, sw, _ = sd.isocalendar()
                    on_time = (dy, dw) <= (sy, sw)
            picking.delivered_on_time = on_time

    @api.depends("date_done")
    def _compute_delivery_month(self):
        for picking in self:
            if picking.date_done:
                dt_local = fields.Datetime.context_timestamp(picking, picking.date_done)
                picking.delivery_month = dt_local.strftime("%Y-%m")
            else:
                picking.delivery_month = ""

    @api.depends("delivery_month", "delivered_on_time", "state")
    def _compute_service_rate_percent(self):
        months = set(self.mapped("delivery_month")) - {""}
        domain = [
            ("state", "=", "done"),
            "|",
            ("planned_date_reason", "!=", "customer"),
            ("planned_date_reason", "=", False),
        ]
        if months:
            domain.append(("delivery_month", "in", list(months)))
        group_data = self.env["stock.picking"]._read_group(
            domain=domain,
            groupby=["delivery_month", "delivered_on_time"],
            aggregates=["__count"],
        )
        stats = {}
        for (month, on_time, count) in group_data:
            stats.setdefault(month, {"total": 0, "on_time": 0})
            stats[month]["total"] += count
            if on_time:
                stats[month]["on_time"] += count
        for picking in self:
            month = picking.delivery_month
            if month and month in stats and stats[month]["total"] > 0:
                picking.service_rate_percent = (
                    stats[month]["on_time"] / stats[month]["total"] * 100.0
                )
            else:
                picking.service_rate_percent = 0.0

    @api.depends("scheduled_date")
    def _compute_require_planned_date_reason(self):
        for rec in self:
            orig = rec._origin if rec._origin and rec._origin.id else rec
            rec.require_planned_date_reason = bool(
                orig
                and orig.id
                and rec.scheduled_date
                and rec.scheduled_date != orig.scheduled_date
            )

    @api.depends("picking_type_id.code", "location_dest_id.usage")
    def _compute_is_customer_delivery(self):
        for picking in self:
            picking.is_customer_delivery = picking.picking_type_id.code == "outgoing"

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
