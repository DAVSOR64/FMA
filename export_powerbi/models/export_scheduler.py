import tempfile
import os
import paramiko
import xlsxwriter
from datetime import datetime
from odoo import models, fields, api

class ExportSFTPScheduler(models.Model):
    _name = 'export.sftp.scheduler'
    _description = 'Export automatique vers SFTP'

    @api.model
    def export_data_to_sftp(self):
        config = self.env['export.sftp.config'].search([], limit=1)
        if not config:
            return

        today = datetime.now().strftime('%Y%m%d')
        temp_dir = tempfile.mkdtemp()

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

        # Clients
        clients = self.env['res.partner'].search([('customer_rank', '>', 0)])
        client_data = [(p.name, p.email, p.phone, p.vat) for p in clients]
        client_file = write_xlsx(f'clients_{today}.xlsx', ['Nom', 'Email', 'Téléphone', 'TVA'], client_data)

        # Commandes
        orders = self.env['sale.order'].search([])
        order_data = [(o.name, o.date_order.strftime('%Y-%m-%d'), o.partner_id.name, o.amount_total) for o in orders]
        order_file = write_xlsx(f'commandes_{today}.xlsx', ['Référence', 'Date', 'Client', 'Montant TTC'], order_data)

        # Factures
        invoices = self.env['account.move'].search([('move_type', '=', 'out_invoice')])
        invoice_data = [(i.name, i.invoice_date.strftime('%Y-%m-%d') if i.invoice_date else '', i.partner_id.name, i.amount_total) for i in invoices]
        invoice_file = write_xlsx(f'factures_{today}.xlsx', ['N° Facture', 'Date', 'Client', 'Montant TTC'], invoice_data)

        # Envoi SFTP
        ssh = paramiko.Transport((config.host, config.port))
        ssh.connect(username=config.username, password=config.password)
        sftp = paramiko.SFTPClient.from_transport(ssh)

        for file_path in [client_file, order_file, invoice_file]:
            filename = os.path.basename(file_path)
            sftp.put(file_path, os.path.join(config.path, filename))

        sftp.close()
        ssh.close()
