# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import ftplib
import io
import logging
from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_txt_created = fields.Boolean("Is Customers File Created")
    is_synced_to_ftp = fields.Boolean()
    # Below field is yet to be used, for now considered as ''
    encours_max = fields.Char()

    def _generate_customer_details_file(self):
        """Generate and attach the customer details .txt file."""
        try:
            file_content = self._get_file_content(self)
            self.env['ir.attachment'].create({
                'name': f"{self.name}.txt",
                'type': 'binary',
                'datas': base64.b64encode(file_content.encode('utf-8')),
                'res_model': 'res.partner',
                'res_id': self.id,
                'mimetype': 'text/plain',
                'is_customer_txt': True
            })

            self.is_txt_created = True
        except Exception as e:
            _logger.exception("Failed to create customer file for %s: %s", self.name, e)

    def _get_file_content(self, partner):
        """Get customer details for the .txt file based on given fields."""
        values = [
            partner.x_studio_code_tiers or '',
            partner.name or '',
            (partner.invoice_ids[0].partner_id.country_id.name if partner.invoice_ids else partner.country_id.name) or '',
            partner.phone or '',
            partner.x_studio_commercial or '',
            partner.x_studio_char_field_G6qIE or '',
            partner.encours_max or '',
            partner.x_studio_mode_de_rglement_1 or '',
            (partner.bank_ids[0].bank_id if partner.bank_ids else '') or '',
            (partner.bank_ids[0].acc_number if partner.bank_ids else '') or '',
            (partner.invoice_ids[0].partner_id.zip if partner.invoice_ids else partner.zip) or '',
            (partner.invoice_ids[0].partner_id.street if partner.invoice_ids else partner.street) or '',
            (partner.invoice_ids[0].partner_id.street2 if partner.invoice_ids else partner.street2) or '',
            (partner.invoice_ids[0].partner_id.state_id.name if partner.invoice_ids else partner.state_id.name) or '',
            partner.email or '',
            (partner.invoice_ids[0].partner_id.city if partner.invoice_ids else partner.city) or '',
        ]
        file_content = '\t'.join(values)
        return file_content

    def cron_generate_generate_customer_files(self):
        """Cron to generate customer details .txt file."""
        partners = self.search([('is_txt_created', '=', False)])
        for partner in partners:
            partner._generate_customer_details_file()

    def cron_send_customers_file_to_ftp_server(self):
        """Sync the unsynced customer files to FTP server."""
        IrAttachment = self.env['ir.attachment']
        partners = self.search([
            ('is_txt_created', '=', True),
            ('is_synced_to_ftp', '=', False)
        ])

        for partner in partners:
            try:
                with self.env.cr.savepoint():
                    attachment_txt = IrAttachment.search([
                        ('res_model', '=', 'res.partner'),
                        ('res_id', '=', partner.id),
                        ('is_customer_txt', '=', True)
                    ], limit=1)
                    if attachment_txt:
                        self._sync_file(attachment_txt)
                        partner.is_synced_to_ftp = True
                    else:
                        _logger.warning(f"No .txt attachment found for Partner {partner.name}.")
            except Exception as e:
                _logger.error(f"Failed to sync customer file {partner.name}.txt to FTP server: {e}")

    def _sync_file(self, attachment):
        get_param = self.env['ir.config_parameter'].sudo().get_param
        ftp_server_host = get_param('fma_customer_export.ftp_server_host')
        ftp_server_username = get_param('fma_customer_export.ftp_server_username')
        ftp_server_password = get_param('fma_customer_export.ftp_server_password')
        ftp_server_file_path = get_param('fma_customer_export.ftp_server_file_path')
        if not all([ftp_server_host, ftp_server_username, ftp_server_password, ftp_server_file_path]):
            _logger.error("Missing one or more FTP server credentials.")
            return

        attachment_content = base64.b64decode(attachment.datas)
        with ftplib.FTP(ftp_server_host, ftp_server_username, ftp_server_password) as session:
            try:
                session.cwd(ftp_server_file_path)
                session.storbinary('STOR ' + attachment.name, io.BytesIO(attachment_content))

            except ftplib.all_errors as ftp_error:
                _logger.error("FTP error while uploading file %s: %s", attachment.name, ftp_error)
            except Exception as upload_error:
                _logger.error("Unexpected error while uploading file %s: %s", attachment.name, upload_error)
