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

    is_file_txt_created = fields.Boolean("Fichier généré")
    file_txt_creation_time = fields.Datetime()
    ftp_file_synced_time = fields.Datetime()
    is_file_synced_to_ftp = fields.Boolean()

    def action_view_journal_items(self):
        self.ensure_one()
        context = {
            "search_default_posted": 1,
            "search_default_group_by_move": 1,
            "search_default_group_by_account": 1,
        }
        domain = [("move_id", "=", self.id)]
        return {
            "name": "Journal Items",
            "view_mode": "tree",
            "views": [(self.env.ref("account.view_move_line_tree").id, "tree")],
            "res_model": "account.move.line",
            "type": "ir.actions.act_window",
            "target": "current",
            "domain": domain,
            "context": context,
        }

    def action_create_supplier_journal_items_file(self):
        """Attach the journal items .csv file."""
        _logger.warning(">>> ACTION action_create_supplier_journal_items_file appelée ! ids=%s", self.ids)
        _logger.warning(">>> move(s) state=%s move_type=%s is_file_txt_created=%s is_txt_created=%s",
                    self.mapped("state"), self.mapped("move_type"),
                    self.mapped("is_file_txt_created"),
                    self.mapped("is_txt_created") if hasattr(self, "is_txt_created") else "NO_FIELD")
        AccountMoveLine = self.env["account.move.line"]
        IrAttachment = self.env["ir.attachment"]
        for move in self.filtered(
            lambda move: not move.is_txt_created
            #and move.state == "posted"
            and move.move_type in ("in_invoice", "in_refund")
        ):
            try:
                journal_items = AccountMoveLine.search([("move_id", "=", move.id)])
                if not journal_items:
                    _logger.exception("No Journal Items found for invoice ", move.name)
                    continue

                file_content = self._get_file_supplier_content(journal_items, move)
                attachment = IrAttachment.create(
                    {
                        "name": f"{move.name}.csv",
                        "type": "binary",
                        "datas": base64.b64encode(file_content),
                        "res_model": "account.move",
                        "res_id": move.id,
                        "mimetype": "text/csv",
                        "is_invoice_txt": True,
                    }
                )

                # logging CSV file in chatter
                self._log_csv_file_in_chatter(file_content, attachment.name)

                move.is_txt_created = True
                move.txt_creation_time = fields.Datetime.now()
            except Exception as e:
                _logger.exception(
                    "Failed to create journal items file for %s: %s", move.name, e
                )

    def _get_file_supplier_content(self, journal_items, move):
        """Get journal items grouped by account for the .csv file."""
        grouped_items = []
        po_name = ""
        section = ""
        journal = "ACH"
        po = ""
        activite = ""
        centre_de_frais = ""
        mode_de_reglement = ""
        ana = ""
        _logger.warning("=== Avant les lignes ===")
        for line in move.invoice_line_ids:
            _logger.warning(f"=== Parcours ligne {line.id} ===")
            _logger.warning(f"Has purchase_line_id: {bool(line.purchase_line_id)}")
            if line.purchase_line_id and line.purchase_line_id.order_id:
                _logger.warning(f"purchase_line_id trouvé: {line.purchase_line_id}")
                _logger.warning(f"Has order_id: {bool(line.purchase_line_id.order_id)}")
                po = line.purchase_line_id.order_id
                _logger.warning(f"PO trouvé: {po.name}")
                break

        # Essai 2 (fallback) : via l'origine de facture si elle contient le numéro de PO
        if not po and move.invoice_origin:
            po = self.env["purchase.order"].search(
                [("name", "=", move.invoice_origin)], limit=1
            )

        if po:
            po_name = po.name
            # Récupérer l'entrepôt depuis le bon de commande
            warehouse = None

            _logger.warning("=== DEBUG WAREHOUSE ===")
            _logger.warning(f"PO: {po.name}")

            # Vérifier picking_type_id
            if hasattr(po, "picking_type_id"):
                _logger.info(f"picking_type_id existe: {po.picking_type_id}")
                if po.picking_type_id:
                    _logger.info(f"picking_type_id.name: {po.picking_type_id.name}")
                    if hasattr(po.picking_type_id, "warehouse_id"):
                        warehouse = po.picking_type_id.warehouse_id
                        _logger.info(
                            f"warehouse trouvé via picking_type_id: {warehouse}"
                        )
            else:
                _logger.info("picking_type_id n'existe pas")

            # Vérifier warehouse_id direct
            if hasattr(po, "warehouse_id"):
                _logger.warning(f"warehouse_id direct existe: {po.warehouse_id}")
                if po.warehouse_id and not warehouse:
                    warehouse = po.warehouse_id
            else:
                _logger.info("warehouse_id direct n'existe pas")

            # Déterminer la section selon l'entrepôt
            if warehouse:
                _logger.warning(f"Warehouse trouvé - ID: {warehouse.id}")
                _logger.warning(f"Warehouse name: {warehouse.name}")
                _logger.warning(
                    f"Warehouse code: {warehouse.code if hasattr(warehouse, 'code') else 'pas de code'}"
                )

                warehouse_name = warehouse.name or ""
                warehouse_code = (
                    warehouse.code if hasattr(warehouse, "code") else ""
                )

                if (
                    "LA REGRIPIERRE" in warehouse_name
                    or "LA REGRIPIERRE" in warehouse_code
                ):
                    section = "REG"
                    activite = "ALU"
                    _logger.info(f"Section FMA sélectionnée: {section}")
                elif (
                    "LA REMAUDIERE" in warehouse_name
                    or "LA REMAUDIERE" in warehouse_code
                ):
                    section = "REM"
                    activite = "ACI"
                    _logger.info(f"Section F2M sélectionnée: {section}")
                else:
                    section = "REG"
                    activite = "ALU"
                    _logger.info(
                        f"Section par défaut (aucune correspondance): {section}"
                    )
                po_line_affaire = False
                analytic_code_po = ''
                for pol in po.order_line:
                    if (
                        pol.product_id
                        and (pol.product_id.default_code or "").strip().lower() == "affaire"
                    ):
                        po_line_affaire = pol
                        break
                _logger.info(f"Ligne de PO avec affaire : {po_line_affaire}")
                if po_line_affaire:
                    dist = getattr(po_line_affaire, "analytic_distribution", None) or {}
                    if dist:
                        analytic_id = int(next(iter(dist.keys())))
                        aa = self.env["account.analytic.account"].browse(analytic_id)
                        analytic_code_po = (aa.code or aa.name or "") or ""
                    elif (
                        hasattr(po_line_affaire, "analytic_account_id")
                        and po_line_affaire.analytic_account_id
                    ):
                        analytic_code_po = (
                            po_line_affaire.analytic_account_id.code
                            or po_line_affaire.analytic_account_id.name
                            or ""
                        )
                    _logger.info(f"Analytic code PO : {analytic_code_po}")
            else:
                _logger.info(
                    "Aucun warehouse trouvé - utilisation valeur par défaut"
                )
                section = "REG"
                activite = "ALU"

            _logger.warning(f"Section finale: {section}")
            _logger.warning("=== FIN DEBUG WAREHOUSE ===")

        analytic_code = ""
        
        for account_code, items_grouped_by_account in groupby(
            journal_items, key=lambda r: r.account_id.code
        ):
            if account_code:
                # 1) Convertir l’itérateur en liste **tout de suite**
                items = list(items_grouped_by_account)
                name_invoice = move.ref
                # if move.name.startswith(('BILL')) :
                # prefix = move.name[:2]
                # year = move.name[2:6]
                # name_invoice = move.name.replace(f"{prefix}{year}", f"{prefix}{year[2:]}", 1)
                # if move.name.startswith('AV2024'):
                #    name_invoice = move.name.replace('AV2024', 'AV24', 1)

                # Calculer les sommes
                debit_sum = round(
                    sum(item.debit for item in items_grouped_by_account), 2
                )
                credit_sum = round(
                    sum(item.credit for item in items_grouped_by_account), 2
                )

                # 3) Récup analytics sur une ligne "référence" du groupe (ex: la première)

                first_line = items[0] if items else False
                if first_line:
                    # a) Cas v15+ : analytic_distribution (dict {analytic_id: ratio})
                    dist = first_line.analytic_distribution or {}
                    if dist:
                        analytic_id = int(next(iter(dist.keys())))
                        aa = self.env["account.analytic.account"].browse(analytic_id)
                        analytic_code = (aa.code or aa.name or "") or ""
                    # b) Fallback si tu as encore analytic_account_id
                    elif (
                        hasattr(first_line, "analytic_account_id")
                        and first_line.analytic_account_id
                    ):
                        analytic_code = (
                            first_line.analytic_account_id.code
                            or first_line.analytic_account_id.name
                            or ""
                        )
                    
                # Formater les nombres avec une virgule comme séparateur décimal
                formatted_debit = f"{debit_sum:.2f}".replace(".", ",")
                formatted_credit = f"{credit_sum:.2f}".replace(".", ",")
                invoice_date = str(move.invoice_date)
                invoice_date_due = str(move.invoice_date_due)
                items_grouped_by_account = list(items_grouped_by_account)
                centre_de_frais = move.x_studio_centre_de_frais or ""
                ana = f"{section}{centre_de_frais}{activite}"
                grouped_items.append(
                    {
                        "journal": journal,
                        "invoice_date": invoice_date.replace("-", ""),
                        "move_name": name_invoice,
                        "invoice_date_1": invoice_date.replace("-", ""),
                        "due_date": invoice_date_due.replace("-", ""),
                        "account_code": account_code,
                        'mode_de_reglement': move.x_studio_mode_de_reglement_1,
                        "name_and_customer_name": f" {move.partner_id.name} {name_invoice}",
                        "payment_reference": analytic_code or analytic_code_po,
                        "section_axe2": analytic_code.replace("-", "")[:10]
                        if analytic_code
                        else analytic_code_po.replace("-", "")[:10],
                        "section": ana,
                        "section_axe3": str("999999999999"),
                        "debit": formatted_debit,
                        "credit": formatted_credit,
                        "name_odoo" :{move.name}",
                    }
                )

        # configuring fields and rows for CSV Export
        fields = [
            "journal",
            "invoice_date",
            "move_name",
            "invoice_date",
            "due_date",
            "account_code",
            "mode_de_reglement",
            "name_and_customer_name",
            "payment_reference",
            "section_axe2",
            "section",
            "section_axe3",
            "debit",
            "credit",
            "name_odoo",
        ]
        output = io.StringIO()
        csv_writer = csv.writer(output, delimiter=";")

        csv_writer.writerow(fields)
        for row in grouped_items:
            csv_writer.writerow([row.get(field, "") for field in fields])

        csv_data = output.getvalue()
        # removing row headers
        csv_data_without_header = "\n".join(csv_data.split("\n")[1:])
        csv_data_bytes = csv_data_without_header.encode("utf-8")

        return csv_data_bytes

    def _log_csv_file_in_chatter(self, csv_content, file_name):
        csv_base64 = base64.b64encode(csv_content).decode("utf-8")
        file_name = f"{file_name}.csv" if not file_name.endswith(".csv") else file_name
        attachment_id = self.env["ir.attachment"].create(
            {
                "name": file_name,
                "datas": csv_base64,
                "res_model": self._name,
                "res_id": self.id,
            }
        )
        self.message_post(
            attachment_ids=[attachment_id.id],
            body=f"CSV file '{file_name}' exported successfully.",
        )

    def cron_generate_supplier_journal_items_file(self):
        """Cron to generate journal items csv file."""
        invoices = self.env["account.move"].search(
            [("state", "=", "posted"), ("is_txt_created", "=", False)]
        )
        for invoice in invoices:
            invoice.action_create_supplier_journal_items_file()

    def cron_send_supplier_invoice_to_ftp(self):
        """Sync the unsynced invoices to the FTP server."""
        invoices = self.env["account.move"].search(
            [
                ("is_txt_created", "=", True),
                ("state", "=", "posted"),
                ("is_synced_to_ftp", "=", False),
            ]
        )
        IrAttachment = self.env["ir.attachment"]
        for invoice in invoices:
            try:
                with self.env.cr.savepoint():
                    attachment_csv = IrAttachment.search(
                        [
                            ("res_model", "=", "account.move"),
                            ("res_id", "=", invoice.id),
                            ("is_invoice_txt", "=", True),
                        ],
                        limit=1,
                    )
                    attachment_pdf = IrAttachment.search(
                        [
                            ("res_model", "=", "account.move"),
                            ("res_id", "=", invoice.id),
                            ("mimetype", "like", "application/pdf"),
                            ("name", "ilike", "invoice"),
                        ],
                        limit=1,
                    )

                    if attachment_csv and attachment_pdf:
                        self._sync_file([attachment_csv, attachment_pdf])
                        invoice.write(
                            {
                                "ftp_synced_time": fields.Datetime.now(),
                                "is_synced_to_ftp": True,
                            }
                        )
                    else:
                        if not attachment_csv:
                            _logger.warning(
                                f"No .csv attachment found for Invoice {invoice.name}."
                            )
                        if not attachment_pdf:
                            _logger.warning(
                                f"No PDF attachment found for Invoice {invoice.name}."
                            )
            except Exception as e:
                _logger.error(f"Failed to sync Invoice {invoice.name} to FTP: {e}")

    def _sync_file(self, attachments):
        get_param = self.env["ir.config_parameter"].sudo().get_param
        ftp_server_host = get_param("fma_supplier_invoice_export.ftp_server_host")
        ftp_server_username = get_param(
            "fma_supplier_invoice_export.ftp_server_username"
        )
        ftp_server_password = get_param(
            "fma_supplier_invoice_export.ftp_server_password"
        )
        ftp_server_file_path = get_param(
            "fma_supplier_invoice_export.ftp_server_file_path"
        )
        if not all(
            [
                ftp_server_host,
                ftp_server_username,
                ftp_server_password,
                ftp_server_file_path,
            ]
        ):
            _logger.error("Missing one or more FTP server credentials.")
            return

        for attachment in attachments:
            attachment_content = base64.b64decode(attachment.datas)
            with ftplib.FTP(
                ftp_server_host, ftp_server_username, ftp_server_password
            ) as session:
                try:
                    session.cwd(ftp_server_file_path)
                    session.storbinary(
                        "STOR " + attachment.name, io.BytesIO(attachment_content)
                    )

                except ftplib.all_errors as ftp_error:
                    _logger.error(
                        "FTP error while uploading file %s: %s",
                        attachment.name,
                        ftp_error,
                    )
                except Exception as upload_error:
                    _logger.error(
                        "Unexpected error while uploading file %s: %s",
                        attachment.name,
                        upload_error,
                    )
