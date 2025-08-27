from odoo import models, fields, api

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    delivered_on_time = fields.Boolean(
        string='Livré à temps',
        compute='_compute_delivered_on_time',
        store=True
    )

    delivery_month = fields.Char(
        string="Mois de livraison",
        compute="_compute_delivery_month",
        store=True
    )

    service_rate_percent = fields.Float(
        string="Taux de service (%)",
        compute="_compute_service_rate_percent",
        store=False
    )

    @api.depends('date_done', 'scheduled_date', 'state')
    def _compute_delivered_on_time(self):
        for picking in self:
            on_time = False
            if picking.state == 'done' and picking.date_done and picking.scheduled_date:
                # Convertir dans le fuseau horaire utilisateur et comparer par semaine ISO
                dd_local = fields.Datetime.context_timestamp(picking, picking.date_done).date()
                sd_local = fields.Datetime.context_timestamp(picking, picking.scheduled_date).date()
                dy, dw, _ = dd_local.isocalendar()
                sy, sw, _ = sd_local.isocalendar()
                on_time = (dy == sy and dw == sw)
            picking.delivered_on_time = on_time

    @api.depends('date_done')
    def _compute_delivery_month(self):
        for picking in self:
            if picking.date_done:
                # Utiliser aussi le TZ utilisateur pour le mois “visible”
                dt_local = fields.Datetime.context_timestamp(picking, picking.date_done)
                picking.delivery_month = dt_local.strftime('%Y-%m')
            else:
                picking.delivery_month = ''

    @api.depends('delivery_month')
    def _compute_service_rate_percent(self):
        group_data = self.env['stock.picking'].read_group(
            domain=[('state', '=', 'done')],
            fields=['delivered_on_time'],
            groupby=['delivery_month', 'delivered_on_time']
        )

        stats = {}
        for entry in group_data:
            month = entry['delivery_month']
            count = entry['__count']
            on_time = entry.get('delivered_on_time')
            stats.setdefault(month, {'total': 0, 'on_time': 0})
            stats[month]['total'] += count
            if on_time:
                stats[month]['on_time'] += count

        for picking in self:
            month = picking.delivery_month
            if month and month in stats and stats[month]['total'] > 0:
                picking.service_rate_percent = (
                    stats[month]['on_time'] / stats[month]['total']
                ) * 100
            else:
                picking.service_rate_percent = 0.0
