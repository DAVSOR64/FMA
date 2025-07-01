
import tempfile
import os
import shutil
import base64
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
        """Génère les fichiers Excel pour clients, commandes, factures, et les stocke en pièces jointes"""
        today = datetime.now().strftime('%Y%m%d')
        temp_dir = tempfile.mkdtemp()
        self.env['ir.config_parameter'].sudo().set_param('export_powerbi.tmp_export_dir', temp_dir)
        _logger.info(f"[Export Power BI] Dossier temporaire : {temp_dir}")

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

        def create_attachment(filepath, name):
            with open(filepath, 'rb') as f:
                file_content = f.read()
            self.env['ir.attachment'].create({
                'name': name,
                'type': 'binary',
                'datas': base64.b64encode(file_content),
                'res_model': 'export.sftp.scheduler',
                'res_id': 0,  # Pas de record spécifique
                'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            })
            _logger.info(f"[Export Power BI] Pièce jointe créée : {name}")

        try:
            # Clients
            clients = self.env['res.partner'].search([('customer_rank', '>', 0), ('is_company', '=', True)])
            client_data = [(p.id, p.name, p.email, p.phone, p.vat) for p in clients]
            client_file = write_xlsx(f'clients_{today}.xlsx', ['ID', 'Nom', 'Email', 'Téléphone', 'TVA'], client_data)
            create_attachment(client_file, os.path.basename(client_file))

            # Commandes
            orders = self.env['sale.order'].search([])
            order_data = [(o.id, o.name, o.date_order.strftime('%Y-%m-%d') if o.date_order else '', o.partner_id.id, o.partner_id.name, o.amount_total, o.tag_ids[0].name if o.tag_ids else '') for o in orders]
            order_file = write_xlsx(f'commandes_{today}.xlsx', ['ID', 'Référence', 'Date', 'ID Client', 'Client', 'Montant TTC','Societe'], order_data)
            create_attachment(order_file, os.path.basename(order_file))

            # Lignes de commandes
            order_lines = self.env['sale.order.line'].search([('product_id', '!=', False)])
            order_line_data = [
                (
                    l.id,
                    l.order_id.id,
                    l.order_id.name,
                    l.order_id.date_order.strftime('%Y-%m-%d') if l.order_id.date_order else '',
                    l.order_id.partner_id.id,
                    l.order_id.partner_id.name,
                    l.product_id.id,
                    l.product_id.default_code or '',
                    l.product_id.name or '',
                    l.product_uom_qty,
                    l.price_unit,
                    l.price_subtotal
                ) for l in order_lines
            ]
            order_line_file = write_xlsx(
                f'lignes_commandes_{today}.xlsx',
                ['ID Ligne', 'ID Commande', 'N° Commande', 'Date', 'ID Client', 'Client', 'ID Article', 'Code article', 'Nom article', 'Qté', 'PU HT', 'Sous-total HT'],
                order_line_data
            )
            create_attachment(order_line_file, os.path.basename(order_line_file))

            # Factures
            invoices = self.env['account.move'].search([('move_type', '=', 'out_invoice'), ('state', '=', 'posted')])
            invoice_data = [
                (
                    i.id,
                    i.name,
                    i.invoice_date.strftime('%Y-%m-%d') if i.invoice_date else '',
                    i.partner_id.id,
                    i.partner_id.name,
                    i.amount_total
                ) for i in invoices
            ]
            invoice_file = write_xlsx(
                f'factures_{today}.xlsx',
                ['ID', 'N° Facture', 'Date', 'ID Client', 'Client', 'Montant TTC'],
                invoice_data
            )
            create_attachment(invoice_file, os.path.basename(invoice_file))

            # Lignes de factures
            invoice_lines = self.env['account.move.line'].search([
                ('move_id.move_type', '=', 'out_invoice'),
                ('move_id.state', '=', 'posted'),
                ('product_id', '!=', False)
            ])
            invoice_line_data = [
                (
                    l.id,
                    l.move_id.id,
                    l.move_id.name,
                    l.move_id.invoice_date.strftime('%Y-%m-%d') if l.move_id.invoice_date else '',
                    l.move_id.partner_id.id,
                    l.move_id.partner_id.name,
                    l.product_id.id,
                    l.product_id.default_code or '',
                    l.product_id.name or '',
                    l.quantity,
                    l.price_unit,
                    l.price_subtotal,
                    l.sale_line_ids[0].id if l.sale_line_ids else None
                ) for l in invoice_lines
            ]
            invoice_line_file = write_xlsx(
                f'lignes_factures_{today}.xlsx',
                ['ID Ligne', 'ID Facture', 'N° Facture', 'Date', 'ID Client', 'Client', 'ID Article', 'Code article', 'Nom article', 'Qté', 'PU HT', 'Sous-total HT', 'ID Ligne Commande'],
                invoice_line_data
            )
            create_attachment(invoice_line_file, os.path.basename(invoice_line_file))



        except Exception as e:
            _logger.exception("Erreur lors de la génération des fichiers Power BI : %s", e)

    @api.model
    def cron_send_files_to_sftp(self):
        """Envoie les fichiers Excel générés vers le serveur SFTP."""
        get_param = self.env['ir.config_parameter'].sudo().get_param
    
        host = get_param('fma_powerbi_export.sftp_server_host')
        port = 22  # Ou stocké aussi en config_param si besoin
        username = get_param('fma_powerbi_export.sftp_server_username')
        password = get_param('fma_powerbi_export.sftp_server_password')
        path = get_param('fma_powerbi_export.sftp_server_file_path')

        
        if not all([host, username, password, path]):
            _logger.error("Paramètres SFTP manquants. Vérifiez la configuration dans Paramètres.")
            return
    
        temp_dir = self.env['ir.config_parameter'].sudo().get_param('export_powerbi.tmp_export_dir')
        if not temp_dir or not os.path.exists(temp_dir):
            _logger.warning("Répertoire temporaire introuvable pour l'export.")
            return
    
        try:
            ssh = paramiko.Transport((host, port))
            ssh.connect(username=username, password=password)
            sftp = paramiko.SFTPClient.from_transport(ssh)
    
            for filename in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, filename)
                if os.path.isfile(file_path):
                    sftp.put(file_path, os.path.join(path, filename))
                    _logger.info("Fichier %s envoyé sur le SFTP.", filename)
    
            sftp.close()
            ssh.close()
            shutil.rmtree(temp_dir)
            _logger.info("Répertoire temporaire supprimé après envoi.")
    
        except Exception as e:
            _logger.exception("Erreur lors de l'envoi des fichiers vers le SFTP : %s", e)
