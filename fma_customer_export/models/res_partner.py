# -*- coding: utf-8 -*-

import base64
import io
import logging
import paramiko
from odoo import _, fields, models
from markupsafe import Markup

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_included_in_customers_export_file = fields.Boolean()

    # ⚠️ TEMPORAIRE : commenter si problème persiste
    # attachment_ids = fields.Many2many(
    #     "ir.attachment", "partner_attachment_rel", string="Attachments"
    # )

    encours_max = fields.Char()

    def write(self, vals):
        # ✅ FIX : ne toucher au champ QUE s’il est dans vals
        if "is_included_in_customers_export_file" in vals:
            if not vals.get("is_included_in_customers_export_file"):
                vals["is_included_in_customers_export_file"] = False

        return super().write(vals)

    def _get_file_content(self, partners):
        content_lines = []
        for partner in partners:
            line = [
                "PCC",
                "I",
                str(partner.property_account_receivable_id.code or "").ljust(9),
                str(partner.name or "").ljust(35),
                "0NNNN0",
                "     ",
                "ODNNON",
                "          ",
                "0",
                "     ",
                "NN0",
                "     ",
                "A41",
                "           ",
                (
                    str(partner.x_studio_civilit_1 or "").ljust(4)
                    + str(partner.name or "").ljust(89)
                ),
                "0",
                "                             ",
                "FRA",
                str(partner.phone or "").ljust(64),
                str(partner.siret or "").ljust(14),
                "      ",
                str(partner.vat or "").ljust(14),
                "                                                  ",
                "             ",
                "                         ",
                "EUR",
                str(partner.x_studio_mode_de_rglement_dsa.x_name or "").ljust(2),
                str(partner.x_studio_code or "").ljust(2),
                str(partner.bank_ids[0].bank_id.name or "").ljust(24)
                if partner.bank_ids and partner.bank_ids[0].bank_id
                else "                        ",
                "                        ",
                str(partner.bank_ids[0].acc_number or "").ljust(23)
                if partner.bank_ids and partner.bank_ids[0].acc_number
                else "                       ",
                "OOO",
                "             ",
                "O0000",
                "                     ",
                "0",
                "            ",
                "0",
                "            ",
                "0",
                "     ",
                "NO1",
                "                               ",
                str(
                    partner.invoice_ids[0].partner_id.zip
                    if partner.invoice_ids
                    else partner.zip or ""
                ).ljust(20),
                "                              ",
                "@                             ",
                "@                       ",
                "@                       ",
                "@    ",
                "@    ",
                "@          ",
                "@ ",
                "@                             ",
                "@                       ",
                "@                       ",
                "@    ",
                "@    ",
                "@          ",
                "@ ",
                "1",
                "                                  ",
                "                    ",
                "                                  ",
                "                    ",
                "                                  ",
                "                    ",
                "        ",
                "                    ",
                "N",
                "                                                            ",
                "      ",
                "@        ",
                str(
                    partner.invoice_ids[0].partner_id.street
                    if partner.invoice_ids
                    else partner.street or ""
                ).ljust(38),
                str(
                    partner.invoice_ids[0].partner_id.street2
                    if partner.invoice_ids and partner.invoice_ids[0].partner_id.street2
                    else partner.street2 or ""
                ).ljust(38),
                str(
                    partner.invoice_ids[0].partner_id.state_id.name
                    if partner.invoice_ids
                    and partner.invoice_ids[0].partner_id.state_id
                    else partner.state_id.name or ""
                ).ljust(38),
                str(partner.email or "").ljust(100),
                "                            ",
                str(
                    partner.invoice_ids[0].partner_id.city
                    if partner.invoice_ids
                    else partner.city or ""
                ).ljust(26),
                "00001",
                "papier ",
                "                                                                                    ",
            ]
            content_lines.append("".join(map(str, line)))

        return "\n".join(content_lines)

    def _log_file_for_each_partner(self, partners, file):
        attachment_url = f"/web/content/{file.id}?download=true"

        for partner in partners:
            partner.message_post(
                body=Markup(
                    _(
                        "Customer Details files created: <a href='%s' target='_blank'>%s</a>"
                    )
                )
                % (attachment_url, file.name)
            )

            # ✅ FIX sudo
            partner.sudo().write({
                "is_included_in_customers_export_file": True
            })

    def cron_generate_generate_customer_files(self):
        partners = self.search(
            [
                ("is_included_in_customers_export_file", "=", False),
                ("is_company", "=", True),
            ]
        )

        try:
            file_content = self._get_file_content(partners)

            file_name = (
                f"Customer_Details_{fields.Datetime.now().strftime('%Y-%m-%d')}.txt"
            )

            # ✅ FIX sudo
            file = self.env["ir.attachment"].sudo().create(
                {
                    "name": file_name,
                    "type": "binary",
                    "datas": base64.b64encode(file_content.encode("utf-8")),
                    "res_model": "res.partner",
                    "mimetype": "text/plain",
                    "is_customer_txt": True,
                }
            )

            self._log_file_for_each_partner(partners, file)

        except Exception as e:
            _logger.exception("Erreur export clients: %s", e)

    def cron_send_customers_file_to_sftp_server(self):
        # ✅ FIX sudo
        attachments = self.env["ir.attachment"].sudo().search(
            [
                ("res_model", "=", "res.partner"),
                ("is_customer_txt", "=", True),
                ("is_synced_to_sftp", "=", False),
            ]
        )

        get_param = self.env["ir.config_parameter"].sudo().get_param

        sftp_server_host = get_param("fma_customer_export.sftp_server_host")
        sftp_server_username = get_param("fma_customer_export.sftp_server_username")
        sftp_server_password = get_param("fma_customer_export.sftp_server_password")
        sftp_server_file_path = get_param("fma_customer_export.sftp_server_file_path")

        if not all([
            sftp_server_host,
            sftp_server_username,
            sftp_server_password,
            sftp_server_file_path,
        ]):
            _logger.error("Paramètres SFTP manquants")
            return

        for attachment in attachments:
            try:
                with self.env.cr.savepoint():
                    self._sync_file(
                        attachment,
                        sftp_server_host,
                        sftp_server_username,
                        sftp_server_password,
                        sftp_server_file_path,
                    )

                    attachment.sudo().write({
                        "is_synced_to_sftp": True
                    })

            except Exception as e:
                _logger.error("Erreur SFTP: %s", e)

    def _sync_file(
        self,
        attachment,
        sftp_server_host,
        sftp_server_username,
        sftp_server_password,
        sftp_server_file_path,
    ):
        attachment_content = base64.b64decode(attachment.datas)

        try:
            transport = paramiko.Transport((sftp_server_host, 22))
            transport.connect(
                username=sftp_server_username,
                password=sftp_server_password
            )

            sftp = paramiko.SFTPClient.from_transport(transport)
            sftp.chdir(sftp_server_file_path)

            with io.BytesIO(attachment_content) as file_obj:
                sftp.putfo(file_obj, attachment.name)

        finally:
            if "sftp" in locals():
                sftp.close()
            if "transport" in locals():
                transport.close()
