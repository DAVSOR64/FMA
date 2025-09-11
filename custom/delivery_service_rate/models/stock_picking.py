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

    # ---- Date (type Date) de livraison côté devis/commande (related, stockée) ----
    # Remplace 'sale_id.so_date_de_livraison' par le bon champ si besoin.
    so_date_de_livraison = fields.Date(
        string='Date de livraison (SO)',
        related='sale_id.so_date_de_livraison',
        store=True,
        readonly=True,
    )

    # True si livré avant OU dans la même semaine ISO que la date prévue
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

    @api.depends('date_done', 'so_date_de_livraison', 'state')
    def _compute_delivered_on_time(self):
        for picking in self:
            on_time = False
            if picking.state == 'done' and picking.date_done and picking.so_date_de_livraison:
                # dd: date de fin réelle, convertie en TZ utilisateur puis réduite à la date
                dd = fields.Datetime.context_timestamp(picking, picking.date_done).date()

                # sd: date prévue (type Date). Selon version, ça peut être str -> convertir en date
                sd = picking.so_date_de_livraison
                if isinstance(sd, str):
                    # to_date gère None/str -> date
                    sd = fields.Date.to_date(sd)

                # comparer par semaine ISO
                dy, dw, _ = dd.isocalendar()
                sy, sw, _ = sd.isocalendar()

                # À temps si livré avant OU même semaine que prévu
                on_time = (dy, dw) <= (sy, sw)

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
        # On ne groupe que sur les mois visibles dans self (plus efficace)
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
