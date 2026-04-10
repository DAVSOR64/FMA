from odoo import models, api
from collections import defaultdict

class MrpCapacityCompute(models.Model):
    _name = "mrp.capacity.compute"
    _description = "Compute capacité"

    @api.model
    def refresh_capacity(self):
        self.env["mrp.capacity.charge"].search([]).unlink()

        data = defaultdict(lambda: {"charge": 0.0, "details": []})

        workorders = self.env["mrp.workorder"].search([
            ("state", "not in", ["done", "cancel"]),
            ("date_planned_start", "!=", False),
        ])

        for wo in workorders:
            date = wo.date_planned_start.date()
            wc_id = wo.workcenter_id.id
            duration = wo._get_duration_hours()

            key = (date, wc_id)
            data[key]["charge"] += duration
            data[key]["details"].append((wo, duration))

        for (date, wc_id), vals in data.items():
            wc = self.env["mrp.workcenter"].browse(wc_id)
            capacity = wc.time_efficiency or 8.0

            rec = self.env["mrp.capacity.charge"].create({
                "date": date,
                "workcenter_id": wc_id,
                "capacity": capacity,
                "charge": vals["charge"],
                "load_rate": (vals["charge"] / capacity * 100) if capacity else 0,
            })

            for wo, duration in vals["details"]:
                self.env["mrp.capacity.charge.detail"].create({
                    "capacity_id": rec.id,
                    "workorder_id": wo.id,
                    "duration": duration,
                })
