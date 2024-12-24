# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import io
import logging
import paramiko
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
            line = ['PCC',
                    'I',
                    str(partner.part_code_tiers).ljust(9) or '         ',
                    partner.name.ljust(30) or '                                   ',
                    '0',
                    'N',
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
                    '         ',
                    '0 ',
                    '    ',
                    'N',
                    'N',
                    '0  ',
                    '   ',
                    'A41',
                    '        ',
                    '       ']
            content_lines.append(''.join(map(str, line)))

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

    def cron_send_customers_file_to_sftp_server(self):
        """Sync the unsynced customer files to SFTP server."""
        attachments = self.env['ir.attachment'].search([
            ('res_model', '=', 'ir.attachment'),
            ('is_customer_txt', '=', True),
            ('is_synced_to_sftp', '=', False)
        ])

        # Fetch the SFTP credentials
        get_param = self.env['ir.config_parameter'].sudo().get_param
        sftp_server_host = get_param('fma_customer_export.sftp_server_host')
        sftp_server_username = get_param('fma_customer_export.sftp_server_username')
        sftp_server_password = get_param('fma_customer_export.sftp_server_password')
        sftp_server_file_path = get_param('fma_customer_export.sftp_server_file_path')
        if not all([sftp_server_host, sftp_server_username, sftp_server_password, sftp_server_file_path]):
            _logger.error("Missing one or more SFTP server credentials.")
            return

        for attachment in attachments:
            try:
                with self.env.cr.savepoint():
                    self._sync_file(attachment, sftp_server_host, sftp_server_username, sftp_server_password, sftp_server_file_path)
                    attachment.is_synced_to_sftp = True
            except Exception as e:
                _logger.error(f"Failed to sync customer file {attachment.name}.txt to SFTP server: {e}")

    def _sync_file(self, attachment, sftp_server_host, sftp_server_username, sftp_server_password, sftp_server_file_path):
        """Upload the customers file to the SFTP server."""
        attachment_content = base64.b64decode(attachment.datas)
        try:
            # Create an SFTP connection
            transport = paramiko.Transport((sftp_server_host, 22))
            transport.connect(username=sftp_server_username, password=sftp_server_password)
            sftp = paramiko.SFTPClient.from_transport(transport)
            sftp.chdir(sftp_server_file_path)

            # Upload the file
            with io.BytesIO(attachment_content) as file_obj:
                sftp.putfo(file_obj, attachment.name)
            _logger.info("File %s uploaded successfully to SFTP server.", attachment.name)

        except paramiko.SSHException as sftp_error:
            _logger.error("SFTP error while uploading file %s: %s", attachment.name, sftp_error)
        except Exception as upload_error:
            _logger.error("Unexpected error while uploading file %s: %s", attachment.name, upload_error)
        finally:
            if 'sftp' in locals():
                sftp.close()
            if 'transport' in locals():
                transport.close()
