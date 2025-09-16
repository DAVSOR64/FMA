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
            # =========================================================
            # Clients
            # =========================================================
            clients = self.env['res.partner'].search([('customer_rank', '>', 0), ('is_company', '=', True)])
            client_data = [(
                p.id,
                p.name or '',
                p.email or '',
                p.phone or '',
                p.vat or '',
                p.street or '',
                p.city or '',
                p.zip or '',
                (p.country_id.name or '') if p.country_id else '',
                (p.user_id.name or '') if p.user_id else '',
                bool(p.active),
                ', '.join([c.name for c in p.category_id]) if p.category_id else '',
                p.create_date.strftime('%Y-%m-%d') if p.create_date else '',
                (p.company_id.name or '') if p.company_id else '',
            ) for p in clients]
            client_file = write_xlsx(
                f'clients_{today}.xlsx',
                [
                    'ID', 'Nom', 'Email', 'Téléphone', 'TVA',
                    'Rue', 'Ville', 'Code Postal', 'Pays', 'Commercial',
                    'Actif', 'Catégories', 'Créé le', 'Société'
                ],
                client_data
            )
            create_attachment(client_file, os.path.basename(client_file))

            # =========================================================
            # Commandes
            # =========================================================
            orders = self.env['sale.order'].search([])
            order_data = [(
                o.id,
                o.name or '',
                o.date_order.strftime('%Y-%m-%d') if o.date_order else '',
                o.state or '',
                o.partner_id.id if o.partner_id else '',
                (o.partner_id.name or '') if o.partner_id else '',
                o.amount_total,
                (o.currency_id.name or '') if o.currency_id else '',
                (o.user_id.name or '') if o.user_id else '',
                (o.company_id.name or '') if o.company_id else '',
                ', '.join([t.name for t in o.tag_ids]) if o.tag_ids else '',
                o.origin or '',
                o.confirmation_date.strftime('%Y-%m-%d') if getattr(o, 'confirmation_date', False) else '',
                o.invoice_status or '',
                (o.warehouse_id.name or '') if getattr(o, 'warehouse_id', False) else '',
                (o.incoterm.name or '') if getattr(o, 'incoterm', False) else '',
            ) for o in orders]
            order_file = write_xlsx(
                f'commandes_{today}.xlsx',
                [
                    'ID', 'Référence', 'Date', 'État',
                    'ID Client', 'Client', 'Montant TTC', 'Devise',
                    'Commercial', 'Société', 'Tags', 'Origine',
                    'Validée le', 'Statut de facturation', 'Entrepôt', 'Incoterm'
                ],
                order_data
            )
            create_attachment(order_file, os.path.basename(order_file))

            # =========================================================
            # Lignes de commandes
            # =========================================================
            order_lines = self.env['sale.order.line'].search([('product_id', '!=', False)])
            order_line_data = [(
                l.id,
                l.order_id.id if l.order_id else '',
                (l.order_id.name or '') if l.order_id else '',
                l.order_id.date_order.strftime('%Y-%m-%d') if (l.order_id and l.order_id.date_order) else '',
                l.order_id.partner_id.id if (l.order_id and l.order_id.partner_id) else '',
                (l.order_id.partner_id.name or '') if (l.order_id and l.order_id.partner_id) else '',
                l.product_id.id if l.product_id else '',
                (l.product_id.default_code or '') if l.product_id else '',
                (l.product_id.name or '') if l.product_id else '',
                (l.product_id.categ_id.name or '') if (l.product_id and l.product_id.categ_id) else '',
                l.product_uom_qty,
                (l.product_uom.name or '') if l.product_uom else '',
                l.price_unit,
                getattr(l, 'discount', 0.0),
                ', '.join([t.name for t in l.tax_id]) if l.tax_id else '',
                l.price_subtotal,
                (l.currency_id.name or '') if getattr(l, 'currency_id', False) else '',
                (l.order_id.user_id.name or '') if (l.order_id and l.order_id.user_id) else '',
                (l.company_id.name or '') if getattr(l, 'company_id', False) else '',
                getattr(l, 'analytic_account_id', False) and (l.analytic_account_id.name or '') or '',
            ) for l in order_lines]
            order_line_file = write_xlsx(
                f'lignes_commandes_{today}.xlsx',
                [
                    'ID Ligne', 'ID Commande', 'N° Commande', 'Date',
                    'ID Client', 'Client',
                    'ID Article', 'Code article', 'Nom article', 'Catégorie article',
                    'Qté', 'UoM', 'PU HT', 'Remise %', 'Taxes', 'Sous-total HT',
                    'Devise', 'Commercial', 'Société', 'Compte Analytique'
                ],
                order_line_data
            )
            create_attachment(order_line_file, os.path.basename(order_line_file))

            # =========================================================
            # Factures (ventes validées)
            # =========================================================
            invoices = self.env['account.move'].search([('move_type', '=', 'out_invoice'), ('state', '=', 'posted')])
            invoice_data = [(
                i.id,
                i.name or '',
                i.invoice_date.strftime('%Y-%m-%d') if i.invoice_date else '',
                i.invoice_date_due.strftime('%Y-%m-%d') if getattr(i, 'invoice_date_due', False) else '',
                i.payment_state or '',
                i.partner_id.id if i.partner_id else '',
                (i.partner_id.name or '') if i.partner_id else '',
                (i.currency_id.name or '') if i.currency_id else '',
                (i.journal_id.name or '') if i.journal_id else '',
                i.ref or '',
                (i.invoice_user_id.name or '') if getattr(i, 'invoice_user_id', False) else '',
                (i.company_id.name or '') if i.company_id else '',
                i.amount_untaxed,
                i.amount_tax,
                i.amount_total,
            ) for i in invoices]
            invoice_file = write_xlsx(
                f'factures_{today}.xlsx',
                [
                    'ID', 'N° Facture', 'Date', 'Échéance', 'État Paiement',
                    'ID Client', 'Client', 'Devise', 'Journal', 'Référence',
                    'Vendeur', 'Société', 'Montant HT', 'TVA', 'Montant TTC'
                ],
                invoice_data
            )
            create_attachment(invoice_file, os.path.basename(invoice_file))

            # =========================================================
            # Lignes de factures
            # =========================================================
            invoice_lines = self.env['account.move.line'].search([
                ('move_id.move_type', '=', 'out_invoice'),
                ('move_id.state', '=', 'posted'),
                ('product_id', '!=', False)
            ])
            invoice_line_data = [(
                l.id,
                l.move_id.id if l.move_id else '',
                (l.move_id.name or '') if l.move_id else '',
                l.move_id.invoice_date.strftime('%Y-%m-%d') if (l.move_id and l.move_id.invoice_date) else '',
                l.move_id.partner_id.id if (l.move_id and l.move_id.partner_id) else '',
                (l.move_id.partner_id.name or '') if (l.move_id and l.move_id.partner_id) else '',
                (l.move_id.journal_id.name or '') if (l.move_id and l.move_id.journal_id) else '',
                l.product_id.id if l.product_id else '',
                (l.product_id.default_code or '') if l.product_id else '',
                (l.product_id.name or '') if l.product_id else '',
                (l.product_id.categ_id.name or '') if (l.product_id and l.product_id.categ_id) else '',
                l.quantity,
                (getattr(l, 'product_uom_id', False) and (l.product_uom_id.name or '')) or '',
                l.price_unit,
                ', '.join([t.name for t in getattr(l, 'tax_ids', [])]) if getattr(l, 'tax_ids', False) else '',
                l.price_subtotal,
                (l.currency_id.name or '') if getattr(l, 'currency_id', False) else '',
                (l.account_id.code or '') if getattr(l, 'account_id', False) else '',
                getattr(l, 'analytic_account_id', False) and (l.analytic_account_id.name or '') or '',
                (l.sale_line_ids[0].id if l.sale_line_ids else ''),
            ) for l in invoice_lines]
            invoice_line_file = write_xlsx(
                f'lignes_factures_{today}.xlsx',
                [
                    'ID Ligne', 'ID Facture', 'N° Facture', 'Date',
                    'ID Client', 'Client', 'Journal',
                    'ID Article', 'Code article', 'Nom article', 'Catégorie article',
                    'Qté', 'UoM', 'PU HT', 'Taxes', 'Sous-total HT',
                    'Devise', 'Compte', 'Compte Analytique', 'ID Ligne Commande'
                ],
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
