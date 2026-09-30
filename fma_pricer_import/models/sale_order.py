# -*- coding: utf-8 -*-
"""Bouton Import Pricer sur le devis."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    pricer_import_ids = fields.One2many(
        "sqlite.connector",
        "target_sale_order_id",
        string="Imports Pricer",
        readonly=True,
    )
    pricer_import_count = fields.Integer(
        string="Nb imports",
        compute="_compute_pricer_import_count",
    )

    @api.depends("pricer_import_ids")
    def _compute_pricer_import_count(self):
        for order in self:
            order.pricer_import_count = len(order.pricer_import_ids)

    def action_open_pricer_import(self):
        """Ouvre le wizard de depot du fichier de chiffrage."""
        self.ensure_one()
        if self.state not in ("draft", "sent"):
            raise UserError(
                _(
                    "L'import Pricer n'est possible que sur un devis non "
                    "confirme (devis %s).",
                    self.display_name,
                )
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Import Pricer - %s", self.name),
            "res_model": "fma.pricer.import.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_order_id": self.id,
                "default_description": _("Import Pricer %s", self.name),
            },
        }

    def action_view_pricer_imports(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Imports Pricer"),
            "res_model": "sqlite.connector",
            "domain": [("target_sale_order_id", "=", self.id)],
            "view_mode": "list,form",
        }
