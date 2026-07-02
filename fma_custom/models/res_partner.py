# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Business rule migrated from the Odoo Studio server action
"Fichier clients Iziqo" (staging DB, audited 2026-07-02).
See STUDIO_AUDIT.md at the repo root for the full inventory.
"""
import datetime

from odoo import models

IZIQO_HEADER = (
    "Code client;Nom;Telephone;Email;SIRET;TVA;Adresse;CP;Ville;Pays;"
    "Commercial;ID Employe Commercial;Adresse livraison;CP livraison;"
    "Ville livraison;Pays livraison"
)


class ResPartner(models.Model):
    _inherit = "res.partner"

    def action_export_iziqo_customers(self):
        """Exports every company customer to a CSV attachment, regardless of
        which partner the button was clicked from (matches the original
        Studio action, which ignored the triggering record)."""
        lines = [IZIQO_HEADER]

        partners = self.env["res.partner"].search(
            [("customer_rank", ">", 0), ("is_company", "=", True)]
        )

        for partner in partners:
            delivery = self.env["res.partner"].search(
                [("parent_id", "=", partner.id), ("type", "=", "delivery")], limit=1
            )

            commercial = partner.x_studio_commercial_1
            employee_id = ""
            if commercial:
                employee = self.env["hr.employee"].search([("id", "=", commercial.id)], limit=1)
                if not employee:
                    employee = self.env["hr.employee"].search([("user_id", "=", commercial.id)], limit=1)
                if employee:
                    employee_id = str(employee.id)

            lines.append(
                ";".join(
                    [
                        str(partner.ref or "").replace(";", ","),
                        str(partner.name or "").replace(";", ","),
                        str(partner.phone or "").replace(";", ","),
                        str(partner.email or "").replace(";", ","),
                        str(partner.siret or "").replace(";", ","),
                        str(partner.vat or "").replace(";", ","),
                        str(partner.street or "").replace(";", ","),
                        str(partner.zip or "").replace(";", ","),
                        str(partner.city or "").replace(";", ","),
                        str(partner.country_id.name or "").replace(";", ","),
                        str(commercial.name or "").replace(";", ",") if commercial else "",
                        employee_id,
                        str(delivery.street or "").replace(";", ","),
                        str(delivery.zip or "").replace(";", ","),
                        str(delivery.city or "").replace(";", ","),
                        str(delivery.country_id.name or "").replace(";", ","),
                    ]
                )
            )

        csv_content = "\n".join(lines)

        self.env["ir.attachment"].sudo().create(
            {
                "name": "customers_{}.csv".format(datetime.date.today()),
                "type": "binary",
                "raw": csv_content.encode("utf-8"),
                "mimetype": "text/csv",
                "res_model": "res.partner",
            }
        )
