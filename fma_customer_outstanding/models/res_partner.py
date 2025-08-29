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
            #get_param = self.env['ir.config_parameter'].sudo().get_param
            #ftp_server_host = get_param('fma_customer_outstanding.ftp_server_host')
            #ftp_server_username = get_param('fma_customer_outstanding.ftp_server_username')
            #ftp_server_password = get_param('fma_customer_outstanding.ftp_server_password')
            #ftp_server_file_path = get_param('fma_customer_outstanding.ftp_server_file_path')
            ftp_server_host = '194.206.49.72'
            ftp_server_username = 'csproginov'
            ftp_server_password = 'g%tumR/n49:1=5qES6CT'
            ftp_server_file_path = 'FMA/IN/'
            

            _logger.warning("**********host********* %s " % ftp_server_host )
            _logger.warning("**********username********* %s " % ftp_server_username )
            _logger.warning("**********password********* %s " % ftp_server_password )
            _logger.warning("**********path********* %s " % ftp_server_file_path )
            if not all([ftp_server_host, ftp_server_username, ftp_server_password, ftp_server_file_path]):
                _logger.error("Missing one or more FTP server credentials.")
                return

            filename = 'ENCOURS_DAte.csv'
            try :
                transport = paramiko.Transport((ftp_server_host, 22))
                transport.connect(username=ftp_server_user, password=ftp_server_password)
                sftp = paramiko.SFTPClient.from_transport(transport)
                sftp.chdir(ftp_server_file_path)
        
                # Téléchargement dans un fichier temporaire
                with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                    local_path = tmp_file.name
                sftp.get(filename, local_path)  
        
                sftp.close()
                transport.close()
        
                # Lecture du contenu dans un buffer
                with open(local_path, 'rb') as f:
                    file_content = io.BytesIO(f.read())
        
                os.remove(local_path)  # Nettoyage du fichier temporaire
        
                file_content.seek(0)
                self._update_invoices(file_content)

                _logger.warning("Fichiers disponibles dans le dossier : %s", sftp.listdir())
            
            except Exception as sftp_error:
                _logger.error("Fichiers disponibles dans le dossier : %s", sftp.listdir())
                _logger.error("Error while connecting or retrieving file from SFTP: %s", sftp_error)

        except Exception as e:
            _logger.error("Failed to download customer file %s to SFTP server: %s", filename, e)
            
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
