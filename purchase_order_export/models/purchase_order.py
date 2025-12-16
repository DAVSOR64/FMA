# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import io
import logging
import paramiko
import psycopg2
import xlsxwriter
import html
from io import BytesIO

from odoo import SUPERUSER_ID, api, fields, models, registry, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    is_xml_created = fields.Boolean(default=False, readonly=True)
    xml_creation_time = fields.Datetime(readonly=True)
    sftp_synced_time = fields.Datetime("Send to SFTP", readonly=True)
    shipping_partner_id = fields.Many2one("res.partner")
    customer_delivery_address = fields.Char(
        compute="_get_default_customer_delivery_address", readonly=False
    )
    so_ral = fields.Char(string="RAL :")
    so_riche_en_zinc = fields.Selection(
        [("yes", "Oui"), ("no", "Non")],
        string="Riche en Zinc",
        default="no",
        required=True,
    )

    # -------------------------------------------------------------
    # COMPUTE
    # -------------------------------------------------------------
    @api.depends("shipping_partner_id")
    def _get_default_customer_delivery_address(self):
        shipping_number_to_address = {
            "130172": "LA REGRIPPIERE",
            "175269": "LA REMAUDIERE",
        }
        for order in self:
            if order.shipping_partner_id:
                delivery_address = order.shipping_partner_id.shipping_number
                order.customer_delivery_address = shipping_number_to_address.get(
                    delivery_address, ""
                )

    # -------------------------------------------------------------
    # EXISTING EXPORTS
    # -------------------------------------------------------------
    def _generate_xml_content(self, po):
        body = self.env["ir.qweb"]._render(
            "purchase_order_export.purchase_order_sftp_export_template", {"po": po}
        )
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        return body.encode("utf-8"), "text/xml", "xml"

    def _generate_xml_v2_content(self, po):
        body = self.env["ir.qweb"]._render(
            "purchase_order_export.purchase_order_sftp_export_template_v2", {"po": po}
        )
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        return body.encode("utf-8"), "text/xml", "xml"

    def _generate_xlsx_content(self, po):
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        worksheet = workbook.add_worksheet("Purchase Order")

        headers = [
            "Clientnr", "Article", "Clc1", "Cls1", "Clc2", "Cls2",
            "Leng", "Quantity", "L-prof", "Reference", "Ordernumber",
            "Line", "Expdeldate", "Textinfo", "PD",
            "UnitPrice", "TotalPrice", "Discount", "Required",
        ]

        for col, header in enumerate(headers):
            worksheet.write(0, col, header)

        for row, line in enumerate(po.order_line, start=1):
            worksheet.write(row, 0, "LK001320")
            worksheet.write(row, 1, line.product_id.x_studio_color_logikal or "")
            worksheet.write(row, 2, line.product_id.clc1 or "")
            worksheet.write(row, 3, line.product_id.cls1 or "")
            worksheet.write(row, 4, line.product_id.clc2 or "")
            worksheet.write(row, 5, line.product_id.cls2 or "")
            worksheet.write(row, 6, line.product_id.x_studio_longueur_m or 0.0)
            worksheet.write(row, 7, line.product_qty or 0.0)
            worksheet.write(row, 8, "3")
            worksheet.write(row, 9, "CLG PONCIN porte double")
            worksheet.write(row, 10, po.name or "")
            worksheet.write(row, 11, row)
            worksheet.write(row, 12, str(po.date_planned) or "")
            worksheet.write(row, 13, line.product_id.name or "")
            worksheet.write(row, 14, "test")
            worksheet.write(row, 15, line.price_unit or 0.0)
            worksheet.write(row, 16, line.price_subtotal or 0.0)
            worksheet.write(row, 17, line.discount or 0.0)
            worksheet.write(row, 18, "5,37")

        workbook.close()
        output.seek(0)
        return (
            output.read(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "xlsx",
        )

    # -------------------------------------------------------------
    # XML JANNEAU / DIAPASON (CORRIGÉ)
    # -------------------------------------------------------------
    def _generate_xml_janneau_content(self, po):
        now = fields.Datetime.now()
        creation_date = fields.Date.to_string(now.date())
        creation_time = now.strftime("%H:%M:%S")

        body = self.env["ir.qweb"]._render(
            "purchase_order_export.purchase_order_janneau_template",
            {
                "po": po,
                "creation_date": creation_date,
                "creation_time": creation_time,
            },
        )

        # QWeb peut renvoyer bytes ou str
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")

        # 🔥 CORRECTION CRITIQUE : déséchapper le HTML
        body = html.unescape(body)

        # Nettoyage BOM / retours avant le XML
        body = body.lstrip("\ufeff\r\n\t ")

        xml_str = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE xml>\n'
            + body
        )

        return xml_str.encode("utf-8"), "text/xml", "xml"

    # -------------------------------------------------------------
    # ACTION EXPORT
    # -------------------------------------------------------------
    @api.model
    def action_export(self):
        action = self.env["ir.actions.actions"]._for_xml_id(
            "purchase_order_export.po_export_action"
        )
        action["context"] = {
            "active_id": self.env.context["active_id"],
            "active_model": self.env.context["active_model"],
        }
        return action

    def action_export_order(self, export_format):
        for po in self:
            if po.state in ["done", "cancel"]:
                raise ValidationError(
                    "Purchase order state should not be in 'Cancelled' or 'Done' state."
                )

            if export_format not in ["xlsx", "xml", "xml_v2", "xml_janneau"]:
                raise ValidationError("Unsupported export format.")

            try:
                if export_format == "xlsx":
                    content, mimetype, file_extension = self._generate_xlsx_content(po)
                elif export_format == "xml":
                    content, mimetype, file_extension = self._generate_xml_content(po)
                elif export_format == "xml_v2":
                    content, mimetype, file_extension = self._generate_xml_v2_content(po)
                elif export_format == "xml_janneau":
                    content, mimetype, file_extension = self._generate_xml_janneau_content(po)

                po.write(
                    {
                        "xml_creation_time": fields.Datetime.now(),
                        "is_xml_created": True,
                    }
                )

                filename = (
                    f"JAN-{po.name}.xml"
                    if export_format == "xml_janneau"
                    else f"{export_format.upper()}-{po.name}.{file_extension}"
                )

                self.env["ir.attachment"].create(
                    {
                        "name": filename,
                        "type": "binary",
                        "datas": base64.b64encode(content),
                        "res_model": "purchase.order",
                        "res_id": po.id,
                        "mimetype": mimetype,
                        "is_po_xml": True,
                    }
                )

            except Exception as e:
                po.write({"is_xml_created": False})
                _logger.exception("Failed to export purchase order %s: %s", po.name, e)

    # -------------------------------------------------------------
    # LAQUAGE
    # -------------------------------------------------------------
    so_carton_qty = fields.Integer(string="Qté")
    so_botte_qty = fields.Integer(string="Qté")
    so_botte_length = fields.Float(string="Longueur (en m)")
    so_palette_qty = fields.Integer(string="Qté")
    so_palette_length = fields.Float(string="Longueur (en m)")
    so_palette_depth = fields.Float(string="Profondeur (en m)")
    so_palette_height = fields.Float(string="Hauteur (en m)")
    so_poids_total = fields.Float(string="Poids (en kg)")

    laquage_line_ids = fields.One2many(
        "purchase.order.laquage.line", "order_id", string="Lignes de Laquage"
    )


class PurchaseOrderLaquageLine(models.Model):
    _name = "purchase.order.laquage.line"
    _description = "Ligne de Laquage"
    _inherit = ["mail.thread"]

    order_id = fields.Many2one(
        "purchase.order", string="Commande d'Achat", ondelete="cascade"
    )

    so_repere = fields.Char(string="Réf./Repère")

    _sql_constraints = [
        (
            "so_repere_unique",
            "UNIQUE(so_repere)",
            "La référence doit être unique pour une ligne de laquage !",
        ),
    ]
