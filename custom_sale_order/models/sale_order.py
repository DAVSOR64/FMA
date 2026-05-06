from odoo import models, fields, api


class SaleOrder(models.Model):
    _inherit = "sale.order"

    so_heures_mod_reelles_odoo = fields.Float(
        string="Heures MOD réelles Odoo",
        compute="_compute_so_cout_mod_reel_odoo",
        readonly=True,
    )
    so_cout_mod_reel_odoo = fields.Monetary(
        string="Coût MOD réel Odoo",
        compute="_compute_so_cout_mod_reel_odoo",
        currency_field="currency_id",
        readonly=True,
    )

    def format_amount(self, amount):
        return "{:,.2f}".format(amount).replace(",", " ").replace(".", ",")

    def _get_employee_hourly_cost_for_mod(self, employee):
        if not employee:
            return 0.0

        candidate_fields = [
            "hourly_cost",
            "timesheet_cost",
            "x_hourly_cost",
            "x_studio_cout_horaire",
            "x_studio_cout_horaire_1",
            "x_studio_cot_horaire",
        ]
        for field_name in candidate_fields:
            if field_name in employee._fields:
                return float(employee[field_name] or 0.0)
        return 0.0

    def _compute_so_cout_mod_reel_odoo(self):
        Production = self.env["mrp.production"].sudo()

        for order in self:
            total_hours = 0.0
            total_cost = 0.0

            project = order.x_studio_projet if "x_studio_projet" in order._fields else False
            if not project:
                order.so_heures_mod_reelles_odoo = 0.0
                order.so_cout_mod_reel_odoo = 0.0
                continue

            productions = Production.search([
                ("x_studio_projet_de_la_vente", "=", project.id),
            ])

            for production in productions:
                for workorder in production.workorder_ids:
                    for time_line in workorder.time_ids:
                        duration_hours = (time_line.duration or 0.0) / 60.0
                        hourly_cost = self._get_employee_hourly_cost_for_mod(time_line.employee_id)
                        total_hours += duration_hours
                        total_cost += duration_hours * hourly_cost

            order.so_heures_mod_reelles_odoo = total_hours
            order.so_cout_mod_reel_odoo = total_cost
