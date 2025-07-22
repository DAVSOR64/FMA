from odoo import models, fields

class DeliveryServiceRateMonthly(models.Model):
    _name = 'delivery.service.rate.monthly'
    _description = 'Taux de service livraison par mois'
    _auto = False  # C’est une vue SQL

    delivery_month = fields.Char(string="Mois")
    total_deliveries = fields.Integer(string="Total livraisons")
    on_time_deliveries = fields.Integer(string="Livraisons à temps")
    service_rate = fields.Float(string="Taux de service (%)", store=True)
