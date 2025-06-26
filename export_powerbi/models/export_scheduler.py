import tempfile
import os
import shutil
import paramiko
import xlsxwriter
from datetime import datetime
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class ExportSFTPScheduler(models.Model):
    _name = 'export.sftp.scheduler'
    _description = 'Export automatique vers SFTP'

    @api.model
    def cron_generate_files(self):
        """Génère 3 fichiers Excel (clients, commandes, factures) et les stocke dans /tmp pour envoi futur."""
        today = datetime.now().strftime('%Y%m%d')
        temp_dir = tempfile.mkdtemp()
        self.env['ir.config_parameter'].sudo().set_param('export_powerbi.tmp_export_dir', temp_dir)
        _logger.info(f"Temp dir for export files: {temp_dir}")

        def write_xlsx(filename, headers, rows):
            filepath = os.path.join(temp_dir, filename)
            workbook = xlsxwriter.Workbook(filepath)
            worksheet = workbook.add_worksheet()
            for col, header in enumerate(headers):
                worksheet.write(0, col, header)
            for row_idx, row in enumerate(rows, 1):
                for col_idx, cell in enumerate(row):
                    worksheet.write(row_idx, col_idx, cell)
            workbook.close()
            return filepath

        try:
            # Clients
            clients = self.env['res.partner'].search([('customer_rank', '>', 0)])
            client_data = [(p.name, p.email, p.phone, p.vat) for p in clients]
            write_xlsx(f'clients_{today}.xlsx', ['Nom', 'Email', 'Téléphone', 'TVA'], client_data)

            # Commandes
            orders = self.env['sale.order'].search([])
            order_data = [(o.name, o.date_order.strftime('%Y-%m-%d') if o.date_order else '', o.partner_id.name, o.amount_total) for o in orders]
            write_xlsx(f'commandes_{today}.xlsx', ['Référence', 'Date', 'Client', 'Montant TTC'], order_data)

            # Factures
            invoices = self.env['account.move'].search([('move_type', '=', 'out_invoice')])
            invoice_data = [(i.name, i.invoice_date.strftime('%Y-%m-%d') if i.invoice_date else '', i.partner_id.name, i.amount_total) for i in invoices]
            write_xlsx(f'factures_{today}.xlsx', ['N° Facture', 'Date', 'Client', 'Montant TTC'], invoice_data)

        except Exception as e:
            _logger.exception("Erreur lors de la génération des fichiers Power BI : %s", e)

    @api.model
    def cron_send_files_to_sftp(self):
        """Envoie les fichiers Excel générés vers le serveur SFTP."""
        config = self.env['export.sftp.config'].search([], limit=1)
        if not config:
            _logger.error("Pas de configuration SFTP trouvée.")
            return

        temp_dir = self.env['ir.config_parameter'].sudo().get_param('export_powerbi.tmp_export_dir')
        if not temp_dir or not os.path.exists(temp_dir):
            _logger.warning("Répertoire temporaire introuvable pour l'export.")
            return

        try:
            ssh = paramiko.Transport((config.host, config.port))
            ssh.connect(username=config.username, password=config.password)
            sftp = paramiko.SFTPClient.from_transport(ssh)

            for filename in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, filename)
                if os.path.isfile(file_path):
                    sftp.put(file_path, os.path.join(config.path, filename))
                    _logger.info("Fichier %s envoyé sur le SFTP.", filename)

            sftp.close()
            ssh.close()
            shutil.rmtree(temp_dir)
            _logger.info("Répertoire temporaire supprimé après envoi.")

        except Exception as e:
            _logger.exception("Erreur lors de l'envoi des fichiers vers le SFTP : %s", e)
