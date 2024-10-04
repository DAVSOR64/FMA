# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import csv
import io
import logging
import paramiko
from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    outstandings = fields.Float()

    def cron_update_outstandings(self):
        """Compute outstandings for customers from ENCOURS_DAte.csv of the SFTP server."""
        try:
            get_param = self.env['ir.config_parameter'].sudo().get_param
            sftp_server_host = get_param('fma_customer_outstanding.sftp_host_outstandings')
            sftp_server_username = get_param('fma_customer_outstanding.sftp_username_outstandings')
            sftp_server_password = get_param('fma_customer_outstanding.sftp_password_outstandings')
            sftp_server_file_path = get_param('fma_customer_outstanding.sftp_file_path_outstandings')
            if not all([sftp_server_host, sftp_server_username, sftp_server_password, sftp_server_file_path]):
                _logger.error("Missing one or more SFTP server credentials.")
                return

            filename = 'ENCOURS_DAte.csv'
            try:
                transport = paramiko.Transport((sftp_server_host, 22))
                transport.connect(username=sftp_server_username, password=sftp_server_password)
                sftp = paramiko.SFTPClient.from_transport(transport)
                with sftp.open(f"{sftp_server_file_path}/{filename}", "rb") as remote_file:
                    file_content = io.BytesIO(remote_file.read())

                self._update_customer_outstandings(file_content)
                _logger.info("Customer outstandings updated successfully.")

                # Close the SFTP connection
                sftp.close()
                transport.close()
            except paramiko.SSHException as ssh_error:
                _logger.error("SFTP error while downloading file %s: %s", filename, ssh_error)
            except Exception as download_error:
                _logger.error("Unexpected error while downloading file %s: %s", filename, download_error)
        except Exception as e:
            _logger.error(f"Failed to download customer file {filename} from SFTP server: {e}")

    def _update_customer_outstandings(self, file_content):
        """Parse CSV file and update customer outstandings."""
        # Parse CSV and perform computations
        csv_reader = csv.reader(io.StringIO(file_content.getvalue().decode('utf-8')), delimiter=';')
        customer_codes = []
        rows = []
        for row in csv_reader:
            customer_codes.append(row[0])
            rows.append(row)

        # Fetch all customers in one query
        customers = self.search([('x_studio_compte_proginov', 'in', customer_codes)])
        customer_map = {customer.x_studio_compte_proginov: customer for customer in customers}

        # Update customer outstandings
        for row in rows:
            x_studio_compte_proginov = row[0]
            debit_str = row[1].replace(',', '.')
            credit_str = row[2].replace(',', '.')
            debit = float(debit_str)
            credit = float(credit_str)
            outstandings = debit - credit

            customer = customer_map.get(x_studio_compte_proginov)
            if customer:
                customer.outstandings = outstandings
