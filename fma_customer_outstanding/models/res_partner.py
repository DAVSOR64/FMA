# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import csv
import ftplib
import io
import logging
from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    outstandings = fields.Float()

    def cron_update_outstandings(self):
        """Compute outstandings for customers from ENCOURS_DAte.csv of the FTP server."""
        try:
            get_param = self.env['ir.config_parameter'].sudo().get_param
            ftp_server_host = get_param('fma_customer_outstanding.ftp_server_host')
            ftp_server_username = get_param('fma_customer_outstanding.ftp_server_username')
            ftp_server_password = get_param('fma_customer_outstanding.ftp_server_password')
            ftp_server_file_path = get_param('fma_customer_outstanding.ftp_server_file_path')
            if not all([ftp_server_host, ftp_server_username, ftp_server_password, ftp_server_file_path]):
                _logger.error("Missing one or more FTP server credentials.")
                return

            filename = 'ENCOURS_DAte.csv'
            with ftplib.FTP(ftp_server_host, ftp_server_username, ftp_server_password) as session:
                try:
                    session.cwd(ftp_server_file_path)
                    file_content = io.BytesIO()
                    session.retrbinary(f"RETR {filename}", file_content.write)
                    file_content.seek(0)

                    self._update_customer_outstandings(file_content)
                except ftplib.all_errors as ftp_error:
                    _logger.error("FTP error while downloading file %s: %s", filename, ftp_error)
                except Exception as upload_error:
                    _logger.error("Unexpected error while downloading file %s: %s", filename, upload_error)
                else:
                    session.quit()
        except Exception as e:
            _logger.error(f"Failed to download customer file {filename}.txt to FTP server: {e}")

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
            x_studio_compte = int('411' + row[0])
            debit_str = row[1].replace(',', '.')
            credit_str = row[2].replace(',', '.')
            debit = float(debit_str)
            credit = float(credit_str)
            outstandings = debit - credit

            customer = customer_map.get(x_studio_compte)
            if customer:
                customer.outstandings = outstandings
                customer.x_studio_mtt_echu = debit
                customer.x_studio_mtt_non_echu = credit
