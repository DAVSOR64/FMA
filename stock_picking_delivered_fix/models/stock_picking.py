from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    delivered_on_time = fields.Boolean(
        string="Delivered On Time",
        compute="_compute_delivered_on_time",
        store=True,
        readonly=True,
        copy=False,
    )

    @api.depends("scheduled_date", "date_done", "state")
    def _compute_delivered_on_time(self):
        for picking in self:
            picking.delivered_on_time = bool(
                picking.state == "done"
                and picking.scheduled_date
                and picking.date_done
                and picking.date_done <= picking.scheduled_date
            )
