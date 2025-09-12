# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

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

    # --- Motif + indicateur de changement de date planifiée ---
    planned_date_reason = fields.Selection(
        selection=[
            ('supplier', 'Fournisseur'),
            ('internal', 'Cause interne'),
            ('customer', 'Client'),
        ],
        string="Motif changement",
        help="Obligatoire si la Date planifiée est modifiée.",
        tracking=True,
    )

    planned_date_changed = fields.Boolean(
        string="Date planifiée modifiée",
        default=False,
        readonly=True,
        tracking=True,
    )

    # Helper UI (non stocké) pour détecter le changement en cours d'édition
    require_planned_date_reason = fields.Boolean(
        compute='_compute_require_planned_date_reason',
        store=False,
    )

    # ----- Computes -----

    @api.depends('move_lines.sale_line_id.order_id')
    def _compute_sale_id(self):
        for picking in self:
            orders = picking.move_lines.mapped('sale_line_id.order_id')
            picking.sale_id = orders[:1].id if orders else False

    @api.depends('date_done', 'state', 'sale_id.so_date_de_livraison')
    def _compute_delivered_on_time(self):
        """Compare sale.order.so_date_de_livraison (Date) vs picking.date_done (Datetime, TZ user)."""
        for picking in self:
            on_time = False
            if picking.state == 'done' and picking.date_done and picking.sale_id and picking.sale_id.so_date_de_livraison:
                dd = fields.Datetime.context_timestamp(picking, picking.date_done).date()  # réel (local)
                sd = picking.sale_id.so_date_de_livraison  # prévu (Date sur SO)
                if isinstance(sd, str):
                    sd = fields.Date.to_date(sd)
                dy, dw, _ = dd.isocalendar()
                sy, sw, _ = sd.isocalendar()
                on_time = (dy, dw) <= (sy, sw)
                # Variante "date à date" possible :
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
                picking.service_rate_percent = stats[month]['on_time'] / stats[month]['total'] * 100.0
            else:
                picking.service_rate_percent = 0.0

    @api.depends('scheduled_date')
    def _compute_require_planned_date_reason(self):
        for rec in self:
            orig = rec._origin if rec._origin and rec._origin.id else rec
            rec.require_planned_date_reason = bool(
                orig and orig.id and rec.scheduled_date and rec.scheduled_date != orig.scheduled_date
            )

    def write(self, vals):
        planned_date_changed_now = False
        if 'scheduled_date' in vals:
            new_dt = fields.Datetime.to_datetime(vals.get('scheduled_date')) if vals.get('scheduled_date') else False
            for rec in self:
                old_dt = rec.scheduled_date
                if new_dt and old_dt and new_dt != old_dt:
                    planned_date_changed_now = True
                    reason = vals.get('planned_date_reason') or rec.planned_date_reason
                    if not reason:
                        raise UserError(_("Veuillez sélectionner un 'Motif changement' (Fournisseur, Cause interne ou Client)."))
        res = super().write(vals)
        # Marqueur persistant + log chatter
        if planned_date_changed_now:
            for rec in self:
                rec.sudo().write({'planned_date_changed': True})
                rec.message_post(
                    body=_("Date planifiée modifiée : %s → %s<br/>Motif : %s") % (
                        fields.Datetime.to_string(rec._origin.scheduled_date) if rec._origin else '',
                        fields.Datetime.to_string(rec.scheduled_date),
                        dict(rec._fields['planned_date_reason'].selection).get(rec.planned_date_reason, '') or '-',
                    )
                )
        return res
