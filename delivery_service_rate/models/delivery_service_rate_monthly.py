# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class DeliveryServiceRateMonthly(models.Model):
    _name = "delivery.service.rate.monthly"
    _description = "Taux de service mensuel"
    _auto = False
    _order = "delivery_month desc"

    delivery_month = fields.Char(string="Mois", readonly=True)
    total_deliveries = fields.Integer(string="Livraisons", readonly=True)
    on_time_deliveries = fields.Integer(string="Livraisons à temps", readonly=True)
    service_rate = fields.Float(string="Taux de service (%)", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    ROW_NUMBER() OVER (ORDER BY to_char(date_done, 'YYYY-MM')) AS id,
                    to_char(date_done, 'YYYY-MM') AS delivery_month,
                    COUNT(*)::integer AS total_deliveries,
                    COUNT(CASE WHEN date_done <= scheduled_date THEN 1 END)::integer AS on_time_deliveries,
                    ROUND(
                        (100.0 * COUNT(CASE WHEN date_done <= scheduled_date THEN 1 END)::float
                        / NULLIF(COUNT(*), 0))::numeric,
                        2
                    )::float AS service_rate
                FROM stock_picking
                WHERE state = 'done'
                  AND date_done IS NOT NULL
                  AND scheduled_date IS NOT NULL
                  AND picking_type_id IN (
                      SELECT id FROM stock_picking_type WHERE code = 'outgoing'
                  )
                GROUP BY to_char(date_done, 'YYYY-MM')
            )
        """ % self._table)
