# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import csv
import ftplib
import paramiko
import io
import logging
from datetime import datetime
from odoo import fields, models, Command

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    def cron_update_invoice_status(self):
        """Update status and related fields for invoices from REGLEMENT_DATE.csv on the FTP server."""
        try:
            get_param = self.env['ir.config_parameter'].sudo().get_param
            #ftp_server_host = get_param('fma_invoice_status.ftp_server_host')
            #ftp_server_username = get_param('fma_invoice_status.ftp_server_username')
            #ftp_server_password = get_param('fma_invoice_status.ftp_server_password')
            #ftp_server_file_path = get_param('fma_invoice_status.ftp_server_file_path')
            #ftp_host = self.env['ir.config_parameter'].sudo().get_param('fma_invoice_status.ftp_server_host')
            #ftp_user = self.env['ir.config_parameter'].sudo().get_param('fma_invoice_status.ftp_server_username')
            #ftp_password = self.env['ir.config_parameter'].sudo().get_param('fma_invoice_status.ftp_server_password')
            #ftp_path = self.env['ir.config_parameter'].sudo().get_param('fma_invoice_status.ftp_server_file_path')

            ftp_host = '194.206.49.72'
            ftp_user = 'csproginov'
            ftp_password = 'g%tumR/n49:1=5qES6CT'
            ftp_path = 'IN/'

            _logger.warning("**********host********* %s " % ftp_host )
            _logger.warning("**********username********* %s " % ftp_user )
            _logger.warning("**********password********* %s " % ftp_password )
            _logger.warning("**********path********* %s " % ftp_path )
           
            if not all([ftp_host, ftp_user, ftp_password, ftp_path]):
                _logger.error("Missing one or more FTP server credentials.")
                return

            
            #with ftplib.FTP(ftp_host, ftp_user, ftp_password) as session:
            #    try:
                    #session.cwd(ftp_path)
                    #file_content = io.BytesIO()
                    #session.retrbinary(f"RETR {filename}", file_content.write)
                    #file_content.seek(0)
                    #self._update_invoices(file_content)
                #except ftplib.all_errors as ftp_error:
                #    _logger.error("FTP error while downloading file %s: %s", filename, ftp_error)
                #except Exception as upload_error:
                #    _logger.error("Unexpected error while dealing with invoices %s: %s", filename, upload_error)
            
            filename = 'REGLEMENT_DATE.csv'
            try :
                transport = paramiko.Transport((ftp_host, 22))  # port SFTP
                transport.connect(username=ftp_user, password=ftp_password)
            
                sftp = paramiko.SFTPClient.from_transport(transport)
                sftp.chdir(ftp_path)
                file_content = io.BytesIO()
                
                sftp.getfo(filename, file_content)
                file_content.seek(0)
            
                self._update_invoices(file_content)
            
                sftp.close()
                transport.close()    

                _logger.warning("Fichiers disponibles dans le dossier : %s", sftp.listdir())
            
            except Exception as sftp_error:
                _logger.error("Error while connecting or retrieving file from SFTP: %s", sftp_error)

        except Exception as e:
            _logger.error("Failed to download customer file %s to SFTP server: %s", filename, e)
    
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
        invoices = self.search([('name', 'in', invoice_codes)])
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
