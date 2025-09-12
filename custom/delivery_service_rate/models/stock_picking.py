from odoo import models, fields, api

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # ---- Lien vers la commande/devis source ----
    sale_id = fields.Many2one(
        'sale.order',
        string='Commande de vente',
        compute='_compute_sale_id',
        store=True,
        readonly=True,
    )

    # True si livré avant OU dans la même semaine ISO que la date prévue (SO)
    delivered_on_time = fields.Boolean(
        string='Livré à temps',
        compute='_compute_delivered_on_time',
        store=True,
    )

    # AAAA-MM basé sur la date effective (en TZ utilisateur)
    delivery_month = fields.Char(
        string="Mois de livraison",
        compute="_compute_delivery_month",
        store=True,
    )

    # % du taux de service du mois (non stocké)
    service_rate_percent = fields.Float(
        string="Taux de service (%)",
        compute="_compute_service_rate_percent",
        store=False,
    )

    # ----- Computes -----

    @api.depends('move_lines.sale_line_id.order_id')
    def _compute_sale_id(self):
        """Associer le picking à la sale.order source via les moves."""
        for picking in self:
            orders = picking.move_lines.mapped('sale_line_id.order_id')
            picking.sale_id = orders[:1].id if orders else False

    @api.depends('date_done', 'state', 'sale_id.so_date_de_livraison')
    def _compute_delivered_on_time(self):
        """Compare SO.so_date_de_livraison (Date) vs picking.date_done (Datetime, TZ user)."""
        for picking in self:
            on_time = False
            # conditions minimales
            if picking.state == 'done' and picking.date_done and picking.sale_id and picking.sale_id.so_date_de_livraison:
                # dd: date réelle en TZ utilisateur -> date()
                dd = fields.Datetime.context_timestamp(picking, picking.date_done).date()

                # sd: date prévue sur le SO (champ Date)
                sd = picking.sale_id.so_date_de_livraison
                if isinstance(sd, str):
                    sd = fields.Date.to_date(sd)  # sécurité si string selon version

                # ----- Comparaison par semaine ISO (comme spécifié) -----
                dy, dw, _ = dd.isocalendar()
                sy, sw, _ = sd.isocalendar()
                on_time = (dy, dw) <= (sy, sw)

                # ----- Variante "date à date" (si un jour tu préfères) -----
                # on_time = dd <= sd

            picking.delivered_on_time = on_time

    @api.depends('date_done')
    def _compute_delivery_month(self):
        for picking in self:
            if picking.date_done:
                dt_local = fields.Datetime.context_timestamp(picking, picking.date_done)
                picking.delivery_month = dt_local.strftime('%Y-%m')
            else:
                picking.delivery_month = ''

    @api.depends('delivery_month', 'delivered_on_time', 'state')
    def _compute_service_rate_percent(self):
        """% de pickings livrés à temps pour chaque mois livré (basé sur delivery_month)."""
        months = set(self.mapped('delivery_month')) - {''}
        domain = [('state', '=', 'done')]
        if months:
            domain.append(('delivery_month', 'in', list(months)))

        group_data = self.env['stock.picking'].read_group(
            domain=domain,
            fields=['delivered_on_time'],
            groupby=['delivery_month', 'delivered_on_time'],
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
                    stats[month]['on_time'] / stats[month]['total'] * 100.0
                )
            else:
                picking.service_rate_percent = 0.0
