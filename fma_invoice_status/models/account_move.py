# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import csv
import ftplib
import io
import logging
from datetime import datetime, date
from odoo import fields, models, Command

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    def cron_update_invoice_status(self):
        """Update status and related fields for invoices from REGLEMENT_DATE.csv on the FTP server."""
        try:
            get_param = self.env["ir.config_parameter"].sudo().get_param
            # ftp_server_host = get_param('fma_invoice_status.ftp_server_host')
            # ftp_server_username = get_param('fma_invoice_status.ftp_server_username')
            # ftp_server_password = get_param('fma_invoice_status.ftp_server_password')
            # ftp_server_file_path = get_param('fma_invoice_status.ftp_server_file_path')
            # ftp_host = self.env['ir.config_parameter'].sudo().get_param('fma_invoice_status.ftp_server_host')
            # ftp_user = self.env['ir.config_parameter'].sudo().get_param('fma_invoice_status.ftp_server_username')
            # ftp_password = self.env['ir.config_parameter'].sudo().get_param('fma_invoice_status.ftp_server_password')
            # ftp_path = self.env['ir.config_parameter'].sudo().get_param('fma_invoice_status.ftp_server_file_path')

            ftp_host = "194.206.49.72"
            ftp_user = "csproginov"
            ftp_password = "g%tumR/n49:1=5qES6CT"
            ftp_path = "IN/"

            _logger.warning("**********host********* %s " % ftp_host)
            _logger.warning("**********username********* %s " % ftp_user)
            _logger.warning("**********password********* %s " % ftp_password)
            _logger.warning("**********path********* %s " % ftp_path)

            if not all(
                [
                    ftp_host,
                    ftp_user,
                    ftp_password,
                    ftp_path,
                ]
            ):
                _logger.error("Missing one or more FTP server credentials.")
                return
            filename = ''
            # filename = 'REGLEMENT_DATE.csv'

            # Récupère la date du jour au format ddmmyyyy
            today = date.today().strftime("%d%m%Y")

            # Construit le nom du fichier
            filename = f"REGLEMENT_{today}.csv"
            with ftplib.FTP(
                ftp_host, ftp_user, ftp_password
            ) as session:
                try:
                    session.cwd(ftp_path)
                    file_content = io.BytesIO()
                    session.retrbinary(f"RETR {filename}", file_content.write)
                    file_content.seek(0)

                    self._update_invoices(file_content)
                except ftplib.all_errors as ftp_error:
                    _logger.error(
                        "FTP error while downloading file %s: %s", filename, ftp_error
                    )
                except Exception as upload_error:
                    _logger.error(
                        "Unexpected error while dealing with invoices %s: %s",
                        filename,
                        upload_error,
                    )
        except Exception as e:
            _logger.error(
                f"Failed to download customer file {filename}.txt to FTP server: {e}"
            )

    def _update_invoices(self, file_content):
        """Parse CSV file and update the invoices."""
        file_content.seek(0)
        csv_reader = csv.reader(
            io.StringIO(file_content.getvalue().decode("utf-8")), delimiter=";"
        )
        _logger.warning(
            ">> Taille du buffer : %s octets", file_content.getbuffer().nbytes
        )
        try:
            preview = file_content.getvalue().decode("utf-8", errors="replace")
            _logger.warning(">> Aperçu contenu (utf-8) : %s", preview[:300])
        except Exception as e:
            _logger.error(">> Impossible de décoder le contenu du buffer : %s", e)
        invoice_codes = []
        rows = []
        for row in csv_reader:
            code_csv = row[0]  # ex: FC250123
            
            # On insère "20" après "FC"
            if code_csv.startswith("FC") and len(code_csv) > 2:
                code_odoo = code_csv[:2] + "20" + code_csv[2:]
            else:
                code_odoo = code_csv  # sécurité
    
            invoice_codes.append(code_odoo)
            rows.append(row)
            
            #if row[0] != "":
            #    invoice_codes.append(row[0])
            #    rows.append(row)

        # Fetch all invoices in one query
        invoices = self.search([("name", "in", invoice_codes)])
        invoices_map = {customer.name: customer for customer in invoices}

        # Update invoices
        for row in rows:
            name = row[0]

            # On insère "20" après "FC"
            if name.startswith("FC") and len(name) > 2:
                name_odoo = name[:2] + "20" + name[2:]
            else:
                name_odoo = name  # sécurité
                
            _logger.warning("Facture %s", row[0])
            _logger.warning(" prix %s ", row[3])
            try:
                parsed_date = datetime.strptime(row[1], "%d/%m/%Y").date()
                date_of_payment = fields.Date.to_string(parsed_date)
            except ValueError as e:
                _logger.error(f"Date conversion error for invoice {name}: {str(e)}")
                continue

            sign = row[2].strip()

            amount_str = row[3].replace(",", ".").strip()

            if not amount_str:
                _logger.warning(f"Montant vide pour la facture {name}, ligne ignorée.")
                continue

            try:
                amount = float(amount_str)
            except ValueError:
                _logger.warning(
                    f"Montant non convertible pour la facture {name} : '{amount_str}'"
                )
                continue

            invoice = invoices_map.get(name_odoo)
            _logger.warning("Facture %s", invoice)
            _logger.warning("Signe %s", sign)
            if invoice and sign == "+":
                _logger.warning("Dans le IF")
                try:
                    # S'assurer que la facture est validée
                    if invoice.state != "posted":
                        invoice.action_post()

                    # Forcer un mode de paiement si non trouvé
                    payment_method_line = (
                        invoice.journal_id.inbound_payment_method_line_ids[:1]
                    )
                    if not payment_method_line:
                        manual_payment_method = self.env.ref(
                            "account.account_payment_method_manual_in"
                        )
                        payment_method_line = self.env[
                            "account.payment.method.line"
                        ].create(
                            {
                                "name": "Manual In",
                                "payment_method_id": manual_payment_method.id,
                                "journal_id": invoice.journal_id.id,
                                "payment_type": "inbound",
                            }
                        )
                        _logger.warning(
                            "🔧 Mode de paiement ajouté au journal %s",
                            invoice.journal_id.name,
                        )

                    # Créer l'assistant de paiement
                    PaymentRegister = self.env["account.payment.register"].with_context(
                        active_model="account.move", active_ids=invoice.ids
                    )
                    wizard = PaymentRegister.new(
                        {
                            "payment_date": date_of_payment,
                            "journal_id": invoice.journal_id.id,
                            "amount": amount,
                            "payment_method_line_id": payment_method_line.id,
                        }
                    )

                    wizard._create_payments()
                    _logger.info(
                        "✅ Paiement enregistré pour la facture %s : %.2f €",
                        invoice.name_odoo,
                        amount,
                    )

                except Exception as e:
                    _logger.error(
                        "❌ Échec de création du paiement pour la facture %s : %s",
                        invoice.name_odoo,
                        e,
                    )
