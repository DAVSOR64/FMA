# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    so_cout_mod_reel_odoo = fields.Monetary(
        string="Coût MOD réel Odoo",
        compute="_compute_so_cout_mod_reel_odoo",
        currency_field="currency_id",
        store=False,
        readonly=True,
        help=(
            "Coût MOD réel calculé depuis les temps opérateurs pointés sur les OT "
            "des OF dont le projet est identique au projet de la commande."
        ),
    )

    so_heures_mod_reelles_odoo = fields.Float(
        string="Heures MOD réelles Odoo",
        compute="_compute_so_cout_mod_reel_odoo",
        store=False,
        readonly=True,
        help="Somme des durées opérateurs pointées sur les OT des OF liés au même projet.",
    )

    def _get_employee_hourly_cost(self, employee):
        """Retourne le coût horaire de l'employé.

        Priorité :
        1. champ standard/custom hourly_cost si présent
        2. champ custom x_hourly_cost si présent
        3. 0.0
        """
        if not employee:
            return 0.0

        for field_name in ("hourly_cost", "x_hourly_cost", "x_studio_cout_horaire"):
            if field_name in employee._fields:
                return employee[field_name] or 0.0
        return 0.0

    def _get_project_field_name(self):
        """Champ projet du SO attendu : x_studio_projet."""
        return "x_studio_projet" if "x_studio_projet" in self._fields else False

    @api.depends("x_studio_projet")
    def _compute_so_cout_mod_reel_odoo(self):
        Production = self.env["mrp.production"].sudo()

        mo_project_field = "x_studio_projet_de_la_vente"
        mo_has_project = mo_project_field in Production._fields

        for order in self:
            total_hours = 0.0
            total_cost = 0.0

            so_project_field = order._get_project_field_name()
            project = order[so_project_field] if so_project_field else False

            if project and mo_has_project:
                productions = Production.search([
                    (mo_project_field, "=", project.id),
                ])
            else:
                # Fallback standard Odoo si le projet n'est pas disponible : origin = nom de SO.
                productions = Production.search([
                    ("origin", "=", order.name),
                ])

            for production in productions:
                for wo in production.workorder_ids:
                    for time_line in wo.time_ids:
                        duration_hours = (time_line.duration or 0.0) / 60.0
                        employee = time_line.employee_id if "employee_id" in time_line._fields else False
                        hourly_cost = order._get_employee_hourly_cost(employee)

                        total_hours += duration_hours
                        total_cost += duration_hours * hourly_cost

            order.so_heures_mod_reelles_odoo = total_hours
            order.so_cout_mod_reel_odoo = total_cost
