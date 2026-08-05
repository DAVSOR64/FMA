# -*- coding: utf-8 -*-
"""Wizard de depot du fichier de chiffrage, lance depuis le devis.

Le wizard ne reimplemente pas la lecture du fichier : il cree un
enregistrement ``sqlite.connector`` — qui reste le moteur d'import et le
journal consultable — en lui passant le devis cible, puis declenche
l'import.
"""
import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class FmaPricerImportWizard(models.TransientModel):
    _name = "fma.pricer.import.wizard"
    _description = "Import Pricer dans un devis"

    order_id = fields.Many2one(
        "sale.order",
        string="Devis",
        required=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        related="order_id.partner_id",
        string="Client",
    )
    file = fields.Binary(string="Fichier de chiffrage", required=True)
    filename = fields.Char(string="Nom du fichier")
    description = fields.Char(
        string="Description",
        help="Libelle de l'import dans le journal SQLite Connector.",
    )
    replace_lines = fields.Boolean(
        string="Remplacer les lignes existantes",
        help="Supprime les lignes actuelles du devis avant l'import. "
        "A utiliser pour reimporter un chiffrage corrige.",
    )
    existing_line_count = fields.Integer(
        string="Lignes actuelles",
        compute="_compute_existing_line_count",
    )

    def _compute_existing_line_count(self):
        for wizard in self:
            wizard.existing_line_count = len(
                wizard.order_id.order_line.filtered(lambda l: not l.display_type)
            )

    def action_import(self):
        self.ensure_one()
        order = self.order_id

        if order.state not in ("draft", "sent"):
            raise UserError(
                _(
                    "Le devis %(name)s est a l'etat %(state)s : l'import "
                    "Pricer n'est possible que sur un devis non confirme.",
                    name=order.display_name,
                    state=order.state,
                )
            )
        if not order.partner_id:
            raise UserError(
                _(
                    "Renseignez le client sur le devis %s avant d'importer "
                    "le chiffrage.",
                    order.display_name,
                )
            )

        if self.replace_lines and order.order_line:
            order.order_line.unlink()

        connector = self.env["sqlite.connector"].create(
            {
                "description": self.description
                or _("Import Pricer %s", order.name),
                "file": self.file,
                "filename": self.filename,
                "target_sale_order_id": order.id,
            }
        )
        order.message_post(
            body=_(
                "Import Pricer lance depuis le fichier %s.",
                self.filename or _("(sans nom)"),
            )
        )

        connector.export_data_from_db()

        return {
            "type": "ir.actions.act_window",
            "name": _("Import Pricer"),
            "res_model": "sqlite.connector",
            "res_id": connector.id,
            "view_mode": "form",
            "target": "current",
        }
