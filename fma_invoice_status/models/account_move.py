# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import csv
import io
import logging
import paramiko
from datetime import datetime
from odoo import fields, models, Command

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    def cron_update_invoice_status(self):
        """Update status and related fields for invoices from REGLEMENT_DATE.csv on the SFTP server."""
        get_param = self.env['ir.config_parameter'].sudo().get_param
        sftp_server_host = get_param('fma_invoice_status.sftp_host_invoice_status')
        sftp_server_username = get_param('fma_invoice_status.sftp_username_invoice_status')
        sftp_server_password = get_param('fma_invoice_status.sftp_password_invoice_status')
        sftp_server_file_path = get_param('fma_invoice_status.sftp_file_path_invoice_status')
        if not all([sftp_server_host, sftp_server_username, sftp_server_password, sftp_server_file_path]):
            _logger.error("Missing one or more SFTP server credentials.")
            return

        filename = 'REGLEMENT_DATE.csv'
        try:
            transport = paramiko.Transport((sftp_server_host, 22))
            transport.connect(username=sftp_server_username, password=sftp_server_password)
            sftp = paramiko.SFTPClient.from_transport(transport)
            with sftp.open(f"{sftp_server_file_path}/{filename}", "rb") as remote_file:
                file_content = io.BytesIO(remote_file.read())

            self._update_invoices(file_content)

        except paramiko.SSHException as ssh_error:
            _logger.error("SSH error while downloading file %s: %s", filename, ssh_error)
        except Exception as e:
            _logger.error(f"Failed to download customer file {filename}.txt to SFTP server: {e}")

    def _update_invoices(self, file_content):
        """Parse CSV file and update the invoices."""
        csv_reader = csv.reader(io.StringIO(file_content.getvalue().decode('utf-8')), delimiter=';')
        invoice_codes = []
        rows = []
        for row in csv_reader:
            if row[1] != '':
                invoice_codes.append(row[0])
                rows.append(row)

        # Fetch all invoices in one query
        invoices = self.search([('name', 'in', invoice_codes), ('state', '!=', 'posted')])
        invoices_map = {customer.name: customer for customer in invoices}
        # Update invoices
        for row in rows:
            name = row[0]
            try:
                parsed_date = datetime.strptime(row[1], '%d/%m/%Y').date()
                date_of_payment = fields.Date.to_string(parsed_date)
            except ValueError as e:
                _logger.error(f"Date conversion error for invoice {name}: {str(e)}")
                continue
            sign = row[2]
            amount = float(row[3].replace(',', '.'))

            invoice = invoices_map.get(name)
            if invoice:
                if sign == '+':
                    invoice.write({
                        'invoice_line_ids': [Command.create({
                            'name': 'Additional Charges',
                            'quantity': 1,
                            'price_unit': amount,
                            'account_id': invoice.journal_id.default_account_id.id,
                        })]
                    })
                    invoice.action_post()
                    invoice.invoice_date = date_of_payment
