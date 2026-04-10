from odoo import models, fields

class MrpCapacityCharge(models.Model):
    _name = "mrp.capacity.charge"
    _description = "Capacité vs charge"
    _order = "date, workcenter_id"

    date = fields.Date("Date", required=True)
    workcenter_id = fields.Many2one("mrp.workcenter", "Poste", required=True)

    capacity = fields.Float("Capacité (h)")
    charge = fields.Float("Charge (h)")
    load_rate = fields.Float("Taux (%)")

    detail_ids = fields.One2many(
        "mrp.capacity.charge.detail",
        "capacity_id",
        string="Détail"
    )

class MrpCapacityChargeDetail(models.Model):
    _name = "mrp.capacity.charge.detail"
    _description = "Détail charge"

    capacity_id = fields.Many2one("mrp.capacity.charge", ondelete="cascade")
    workorder_id = fields.Many2one("mrp.workorder")
    duration = fields.Float("Durée (h)")
