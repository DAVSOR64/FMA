# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import ftplib
import io
import logging
from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_included_in_customers_export_file = fields.Boolean()
    attachment_ids = fields.Many2many('ir.attachment', 'partner_attachment_rel', string='Attachments')
    # Below field is yet to be used, for now considered as ''
    encours_max = fields.Char()

    def write(self, vals):
        if not vals.get('is_included_in_customers_export_file'):
            vals['is_included_in_customers_export_file'] = False
        return super(ResPartner, self).write(vals)

    def _get_file_content(self, partners):
        """Get customer details for the .txt file based on given fields."""
        content_lines = []
        for partner in partners:
            line = [
                'PCC',
                'I',
                partner.x_studio_code_tiers or '',
                partner.name or '',
                '0',
                ' ',
                'N',
                'N',
                'N',
                '0     ',
                'O',
                'D',
                'N',
                'N',
                'O',
                'N',
                ' ',
                '          ',
                '0 ',
                ' ',
                '   ',
                'N',
                'N',
                '0  ',
                '   ',
                'A41',
                '   ',
                '        ',
                '    ',
                partner.name or '',
                '                              ',
                '                              ',
                '0    ',
                '                        ',
                (partner.invoice_ids[0].partner_id.country_id.name if partner.invoice_ids else partner.country_id.name) or '',
                partner.phone or '',
                '                    ',
                '                    ',
                ' ',
                partner.x_studio_char_field_G6qIE or '',
                '      ',
                ' ',
                ' ',
                partner.x_studio_commercial or '',
                partner.encours_max or '',
                'EUR',
                partner.x_studio_mode_de_rglement_1 or '',
                ' ',
                ' ',
                '                        ',
                (partner.bank_ids[0].bank_id.name if partner.bank_ids else '') or '',
                ' ',
                (partner.bank_ids[0].acc_number if partner.bank_ids else '') or '',
                ' ',
                ' ',
                ' ',
                ' ',
                ' ',
                ' ',
                ' ',
                ' ',
                ' ',
                '   ',
                '               ',
                '0',
                '0',
                '0     ',
                ' ',
                ' ',
                ' ',
                ' ',
                (partner.invoice_ids[0].partner_id.zip if partner.invoice_ids else partner.zip) or '',
                ' ',
                '@                             ',
                '@                       ',
                '@                       ',
                '@    ',
                '@    ',
                '@          ',
                '@ ',
                '@                             ',
                '@                       ',
                '@                       ',
                '@    ',
                '@    ',
                '@          ',
                '@ ',
                '1',
                '                                  ',
                '                    ',
                '                                  ',
                '                    ',
                '                                  ',
                '                    ',
                'NAF',
                ' ',
                ' ',
                '                                                            ',
                '        ',
                '@        ',
                (partner.invoice_ids[0].partner_id.street if partner.invoice_ids else partner.street) or '',
                (partner.invoice_ids[0].partner_id.street2 if partner.invoice_ids else partner.street2) or '',
                (partner.invoice_ids[0].partner_id.state_id.name if partner.invoice_ids else partner.state_id.name) or '',
                partner.email or '',
                '@                            ',
                (partner.invoice_ids[0].partner_id.city if partner.invoice_ids else partner.city) or '',
                '1'
            ]
            content_lines.append('\t'.join(line))

        return '\n'.join(content_lines)

    def _log_file_for_each_partner(self, partners, file):
        """Log the generated file content for each partner."""
        attachment_url = f"/web/content/{file.id}?download=true"
        for partner in partners:
            # Acknowledge in the chatter
            partner.message_post(
                body=_("Customer Details files created: <a href='%s' target='_blank'>%s</a>") % (attachment_url, file.name)
            )
            # Add the file to attachments as well
            partner.attachment_ids = [(4, file.id)]
            # Mark the record as included
            partner.is_included_in_customers_export_file = True

    def cron_generate_generate_customer_files(self):
        """Cron to generate customer details .txt file."""
        partners = self.search([('is_included_in_customers_export_file', '=', False)])
        try:
            file_content = self._get_file_content(partners)
            file_name = f"Customer_Details_{fields.Datetime.now().strftime('%Y-%m-%d')}.txt"
            file = self.env['ir.attachment'].create({
                'name': file_name,
                'type': 'binary',
                'datas': base64.b64encode(file_content.encode('utf-8')),
                'res_model': 'ir.attachment',
                'mimetype': 'text/plain',
                'is_customer_txt': True
            })

            self._log_file_for_each_partner(partners, file)
        except Exception as e:
            _logger.exception("Failed to create customer file for %s: %s", self.name, e)

    def cron_send_customers_file_to_ftp_server(self):
        """Sync the unsynced customer files to FTP server."""
        attachments = self.env['ir.attachment'].search([
            ('res_model', '=', 'ir.attachment'),
            ('is_customer_txt', '=', True),
            ('is_synced_to_ftp', '=', False)
        ])

        for attachment in attachments:
            try:
                with self.env.cr.savepoint():
                    self._sync_file(attachment)
                    attachment.is_synced_to_ftp = True
            except Exception as e:
                _logger.error(f"Failed to sync customer file {attachment.name}.txt to FTP server: {e}")

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
