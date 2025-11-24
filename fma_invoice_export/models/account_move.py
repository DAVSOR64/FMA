# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import datetime
import ftplib
import io
import csv
import logging

from odoo import api, fields, models
from odoo.tools.misc import groupby
from odoo.addons.web.controllers.main import CSVExport

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    is_txt_created = fields.Boolean("Fichier généré")
    txt_creation_time = fields.Datetime()
    ftp_synced_time = fields.Datetime()
    is_synced_to_ftp = fields.Boolean()

    def action_view_journal_items(self):
        self.ensure_one()
        context = {
            'search_default_posted':1,
            'search_default_group_by_move': 1,
            'search_default_group_by_account': 1
        }
        domain = [
            ('move_id', '=', self.id)
        ]
        return {
            'name': 'Journal Items',
            'view_mode': 'tree',
            'views': [(self.env.ref('account.view_move_line_tree').id, 'tree')],
            'res_model': 'account.move.line',
            'type': 'ir.actions.act_window',
            'target': 'current',
            'domain': domain,
            'context': context
        }

    def action_create_journal_items_file(self):
        """Attach the journal items .csv file."""
        AccountMoveLine = self.env['account.move.line']
        IrAttachment = self.env['ir.attachment']
        for move in self.filtered(lambda move: not move.is_txt_created and move.state == 'posted'):
            try:
                journal_items = AccountMoveLine.search([('move_id', '=', move.id)])
                if not journal_items:
                    _logger.exception("No Journal Items found for invoice ", move.name)
                    continue

                file_content = self._get_file_content(journal_items, move)
                attachment = IrAttachment.create({
                    'name': f"{move.name}.csv",
                    'type': 'binary',
                    'datas': base64.b64encode(file_content),
                    'res_model': 'account.move',
                    'res_id': move.id,
                    'mimetype': 'text/csv',
                    'is_invoice_txt': True
                })

                # logging CSV file in chatter
                self._log_csv_file_in_chatter(file_content, attachment.name)

                move.is_txt_created = True
                move.txt_creation_time = fields.Datetime.now()
            except Exception as e:
                _logger.exception("Failed to create journal items file for %s: %s", move.name, e)

    def _get_file_content(self, journal_items, move):
        """Get journal items grouped by account for the .csv file."""
        grouped_items = []
        sale_order_name = ''
        sale_order = None
        section = ''
        journal = 'VTE'
        _logger.warning("**********dans la fonction pour l export facture vente********* "  )
        if move.line_ids and move.line_ids[0].sale_line_ids:
            sale_order = move.line_ids[0].sale_line_ids[0].order_id
            sale_order_name = sale_order.name if sale_order else ''
            _logger.warning("**********Devis********* %s " % sale_order_name )
            if sale_order_name :
               sale_order_name = sale_order_name[:12]
            tag_names = {tag.name for tag in sale_order.tag_ids}
            if 'FMA' in tag_names:
                section = 'REG0701ALU'
            elif 'F2M' in tag_names:
                section = 'REM0701ACI'
        prefix = ''
        year =''
        for account_code, items_grouped_by_account in groupby(journal_items, key=lambda r: r.account_id.code):
            if account_code:
                name_invoice = move.name
                if move.name.startswith(('FC', 'AVV')) and len(move.name) >= 6 :
                    prefix = move.name[:2]
                    year = move.name[2:6]
                    name_invoice = move.name.replace(f"{prefix}{year}", f"{prefix}{year[2:]}", 1)
                #if move.name.startswith('AV2024'):
                #    name_invoice = move.name.replace('AV2024', 'AV24', 1)
            
                # Calculer les sommes
                debit_sum = round(sum(item.debit for item in items_grouped_by_account), 2)
                credit_sum = round(sum(item.credit for item in items_grouped_by_account), 2)
                
                # Formater les nombres avec une virgule comme séparateur décimal
                formatted_debit = f"{debit_sum:.2f}".replace('.', ',')
                formatted_credit = f"{credit_sum:.2f}".replace('.', ',')
                invoice_date = str(move.invoice_date)
                invoice_date_due = str(move.invoice_date_due)
                items_grouped_by_account = list(items_grouped_by_account)
                grouped_items.append({
                    'journal': journal,
                    'invoice_date': invoice_date.replace('-',''),
                    'move_name': name_invoice,
                    'invoice_date_1': invoice_date.replace('-',''),
                    'due_date': invoice_date_due.replace('-',''),
                    'account_code': account_code,
                    'mode_de_regiment': move.inv_mode_de_reglement.replace('L.C.R. A L ACCEPTATION', 'L.C.R. A L ACCEPTATI') if move.inv_mode_de_reglement == 'L.C.R. A L ACCEPTATION' else move.inv_mode_de_reglement,
                    'name_and_customer_name': f'{name_invoice} {move.partner_id.name}',
                    'payment_reference': f'{sale_order_name} {move.x_studio_rfrence_affaire}',
                    'section_axe2': sale_order_name.replace('-', '') if sale_order_name else '',
                    'section': section,
                    'section_axe3': str('999999999999'),
                    'debit': formatted_debit,
                    'credit': formatted_credit
                })

        # configuring fields and rows for CSV Export
        fields = [
            'journal', 'invoice_date', 'move_name', 'invoice_date', 'due_date', 'account_code', 'mode_de_regiment', 'name_and_customer_name', 'payment_reference', 'section_axe2', 'section', 'section_axe3', 'debit', 'credit'
        ]
        output = io.StringIO()
        csv_writer = csv.writer(output, delimiter=';')

        csv_writer.writerow(fields)
        for row in grouped_items:
            csv_writer.writerow([row.get(field, '') for field in fields])

        csv_data = output.getvalue()
        # removing row headers
        csv_data_without_header = '\n'.join(csv_data.split('\n')[1:])
        csv_data_bytes = csv_data_without_header.encode('utf-8')

        return csv_data_bytes

    def _log_csv_file_in_chatter(self, csv_content, file_name):
        csv_base64 = base64.b64encode(csv_content).decode('utf-8')
        file_name = f"{file_name}.csv" if not file_name.endswith('.csv') else file_name
        attachment_id = self.env['ir.attachment'].create({
            'name': file_name,
            'datas': csv_base64,
            'res_model': self._name,
            'res_id': self.id,
        })
        self.message_post(
            attachment_ids=[attachment_id.id],
            body=f"CSV file '{file_name}' exported successfully."
        )

    def cron_generate_journal_items_file(self):
        """Cron to generate journal items csv file."""
        invoices = self.env['account.move'].search([
            ('state', '=', 'posted'),
            ('is_txt_created', '=', False)
        ])
        for invoice in invoices:
            invoice.action_create_journal_items_file()

    def cron_send_invoice_to_ftp(self):
        """Sync the unsynced invoices to the FTP server."""
        invoices = self.env['account.move'].search([
            ('is_txt_created', '=', True),
            ('state', '=', 'posted'),
            ('is_synced_to_ftp', '=', False)
        ])
        IrAttachment = self.env['ir.attachment']
        for invoice in invoices:
            try:
                with self.env.cr.savepoint():
                    attachment_csv = IrAttachment.search([
                        ('res_model', '=', 'account.move'),
                        ('res_id', '=', invoice.id),
                        ('is_invoice_txt', '=', True)
                    ], limit=1)
                    attachment_pdf = IrAttachment.search([
                        ('res_model', '=', 'account.move'),
                        ('res_id', '=', invoice.id),
                        ('mimetype', 'like', 'application/pdf'),
                        ('name', 'ilike', 'invoice')
                    ], limit=1)

                    if attachment_csv and attachment_pdf:
                        self._sync_file([attachment_csv, attachment_pdf])
                        invoice.write({
                            'ftp_synced_time': fields.Datetime.now(),
                            'is_synced_to_ftp': True
                        })
                    else:
                        if not attachment_csv:
                            _logger.warning(f"No .csv attachment found for Invoice {invoice.name}.")
                        if not attachment_pdf:
                            _logger.warning(f"No PDF attachment found for Invoice {invoice.name}.")
            except Exception as e:
                _logger.error(f"Failed to sync Invoice {invoice.name} to FTP: {e}")

    def _sync_file(self, attachments):
        get_param = self.env['ir.config_parameter'].sudo().get_param
        ftp_server_host = get_param('fma_invoice_export.ftp_server_host')
        ftp_server_username = get_param('fma_invoice_export.ftp_server_username')
        ftp_server_password = get_param('fma_invoice_export.ftp_server_password')
        ftp_server_file_path = get_param('fma_invoice_export.ftp_server_file_path')
        if not all([ftp_server_host, ftp_server_username, ftp_server_password, ftp_server_file_path]):
            _logger.error("Missing one or more FTP server credentials.")
            return

        for attachment in attachments:
            attachment_content = base64.b64decode(attachment.datas)
            with ftplib.FTP(ftp_server_host, ftp_server_username, ftp_server_password) as session:
                try:
                    session.cwd(ftp_server_file_path)
                    session.storbinary('STOR ' + attachment.name, io.BytesIO(attachment_content))

                except ftplib.all_errors as ftp_error:
                    _logger.error("FTP error while uploading file %s: %s", attachment.name, ftp_error)
                except Exception as upload_error:
                    _logger.error("Unexpected error while uploading file %s: %s", attachment.name, upload_error)
