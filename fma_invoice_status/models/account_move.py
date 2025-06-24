# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import csv
import ftplib
import paramiko
import io
import logging
import tempfile
import os
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
            ftp_path = 'FMA/IN/'

            _logger.warning("**********host********* %s " % ftp_host )
            _logger.warning("**********username********* %s " % ftp_user )
            _logger.warning("**********password********* %s " % ftp_password )
            _logger.warning("**********path********* %s " % ftp_path )
           
            if not all([ftp_host, ftp_user, ftp_password, ftp_path]):
                _logger.error("Missing one or more FTP server credentials.")
                return
            
            filename = 'REGLEMENT_DATE.csv'  
            #file_content = io.BytesIO()
            
            try :
                transport = paramiko.Transport((ftp_host, 22))
                transport.connect(username=ftp_user, password=ftp_password)
                sftp = paramiko.SFTPClient.from_transport(transport)
                sftp.chdir(ftp_path)
        
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
    
    def _update_invoices(self, file_content):
        """Parse CSV file and update the invoices."""
        file_content.seek(0)
        csv_reader = csv.reader(io.StringIO(file_content.getvalue().decode('utf-8')), delimiter=';')
        _logger.warning(">> Taille du buffer : %s octets", file_content.getbuffer().nbytes)
        try:
            preview = file_content.getvalue().decode('utf-8', errors='replace')
            _logger.warning(">> Aperçu contenu (utf-8) : %s", preview[:300])
        except Exception as e:
            _logger.error(">> Impossible de décoder le contenu du buffer : %s", e)
        invoice_codes = []
        rows = []
        for row in csv_reader:
            if row[0] != '':
                invoice_codes.append(row[0])
                rows.append(row)

        # Fetch all invoices in one query
        invoices = self.search([('name', 'in', invoice_codes)])
        invoices_map = {customer.name: customer for customer in invoices}

        # Update invoices
        for row in rows:
            name = row[0]
            _logger.warning("Facture %s", row[0])
            _logger.warning(" prix %s ", row[3])
            try:
                parsed_date = datetime.strptime(row[1], '%d/%m/%Y').date()
                date_of_payment = fields.Date.to_string(parsed_date)
            except ValueError as e:
                _logger.error(f"Date conversion error for invoice {name}: {str(e)}")
                continue
                
            sign = row[2].strip() 
            
            amount_str = row[3].replace(',', '.').strip()
            
            if not amount_str:
                _logger.warning(f"Montant vide pour la facture {name}, ligne ignorée.")
                continue
            
            try:
                amount = float(amount_str)
            except ValueError:
                _logger.warning(f"Montant non convertible pour la facture {name} : '{amount_str}'")
                continue

            invoice = invoices_map.get(name)
            _logger.warning("Facture %s", invoice)
            _logger.warning("Signe %s", sign)
            if invoice and sign == '+':
                _logger.warning("Dans le IF")
                # S'assurer que la facture est validée
                if invoice.state != 'posted':
                    invoice.action_post()
            
                # Créer un paiement
                payment_vals = {
                    'payment_type': 'inbound',
                    'partner_type': 'customer',
                    'partner_id': invoice.partner_id.id,
                    'amount': amount,
                    'payment_date': date_of_payment,
                    'journal_id': invoice.journal_id.id,
                    'payment_method_id': self.env.ref('account.account_payment_method_manual_in').id,
                    'ref': f'Paiement automatique pour facture {invoice.name}',
                    'invoice_ids': [Command.link(invoice.id)],
                }
                payment = self.env['account.payment'].create(payment_vals)
                payment.action_post()
            
                _logger.info("Paiement enregistré pour la facture %s : %.2f €", invoice.name, amount)
