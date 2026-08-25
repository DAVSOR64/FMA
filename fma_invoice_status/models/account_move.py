# -*- coding: utf-8 -*-
import base64
import csv
import io
import logging
from datetime import datetime, date

from odoo import fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    def cron_update_invoice_status(self):
        """
        Lit un fichier CSV dans Odoo Documents (ex: REGLEMENT_28012026.csv)
        et enregistre un paiement sur les factures correspondantes.
        Objectif: statut facture = PAYÉ (donc journal de caisse).
        """
        filename = "unknown"
        try:
            today = date.today().strftime("%d%m%Y")
            filename = f"REGLEMENT_{today}.csv"

            file_content = self._get_csv_from_documents(filename)
            if not file_content:
                _logger.warning("Aucun fichier %s trouvé dans Documents.", filename)
                return

            self._update_invoices(file_content)

        except Exception as e:
            _logger.exception("Erreur lors du traitement du fichier %s : %s", filename, e)

    # -------------------------
    # SOURCE CSV = DOCUMENTS
    # -------------------------
    def _get_csv_from_documents(self, filename):
        """
        Récupère le fichier depuis Documents.
        - Si un espace de travail / dossier 'Imports Factures' existe, on cherche dedans en priorité
        - Sinon on cherche globalement dans Documents
        Retourne un io.BytesIO
        """
        if "documents.document" not in self.env:
            _logger.warning("Module Documents non installé : import CSV impossible.")
            return None

        Documents = self.env["documents.document"].sudo()

        folder = self._get_documents_folder("Imports Factures")

        domain = ["|", ("name", "=", filename), ("attachment_id.name", "=", filename)]
        if "type" in Documents._fields:
            domain = [("type", "!=", "folder")] + domain

        doc = Documents.browse()
        if folder:
            doc = Documents.search(
                domain + [("folder_id", "=", folder.id)],
                order="create_date desc",
                limit=1,
            )

        # Si pas trouvé dans le dossier, on tente globalement
        if not doc:
            doc = Documents.search(domain, order="create_date desc", limit=1)

        if not doc:
            return None

        file_bytes = self._get_document_bytes(doc)
        if not file_bytes:
            _logger.warning("Document %s trouvé (id=%s) mais sans contenu.", filename, doc.id)
            return None

        _logger.info("CSV trouvé dans Documents: %s (doc=%s, taille=%s octets)",
                     filename, doc.id, len(file_bytes))
        return io.BytesIO(file_bytes)

    def _get_documents_folder(self, name):
        """
        Depuis Odoo 18, le modèle 'documents.folder' n'existe plus : un dossier est
        un 'documents.document' avec type = 'folder'. On garde l'ancien modèle en
        repli pour rester compatible avec les bases antérieures.
        """
        Documents = self.env["documents.document"].sudo()
        if "type" in Documents._fields:
            return Documents.search([("type", "=", "folder"), ("name", "=", name)], limit=1)
        if "documents.folder" in self.env:
            return self.env["documents.folder"].sudo().search([("name", "=", name)], limit=1)
        return Documents.browse()

    def _get_document_bytes(self, doc):
        """Contenu binaire d'un document, que le stockage passe ou non par une pièce jointe."""
        if doc.attachment_id and doc.attachment_id.datas:
            return base64.b64decode(doc.attachment_id.datas)
        raw = getattr(doc, "raw", False)
        if raw:
            return raw
        datas = getattr(doc, "datas", False)
        if datas:
            return base64.b64decode(datas)
        return None

    # -------------------------
    # UPDATE FACTURES
    # -------------------------
    def _update_invoices(self, file_content):
        """Parse CSV file and update invoices by creating payments."""
        file_content.seek(0)

        raw = file_content.getvalue()
        _logger.warning(">> Taille du buffer : %s octets", len(raw))

        # utf-8-sig pour éviter BOM excel
        text = raw.decode("utf-8-sig", errors="replace")
        _logger.warning(">> Aperçu contenu (utf-8-sig) : %s", text[:300])

        csv_reader = csv.reader(io.StringIO(text), delimiter=";")

        invoice_codes = []
        rows = []

        for row in csv_reader:
            if not row:
                continue

            # Sécurité sur longueur mini
            if len(row) < 4:
                _logger.warning("Ligne CSV incomplète ignorée: %s", row)
                continue

            code_csv = (row[0] or "").strip()
            if not code_csv:
                continue

            # Exemple: FC250123 => FC20250123
            if code_csv.startswith("FC") and len(code_csv) > 2:
                code_odoo = code_csv[:2] + "20" + code_csv[2:]
            else:
                code_odoo = code_csv

            invoice_codes.append(code_odoo)
            rows.append(row)

        if not invoice_codes:
            _logger.warning("Aucune facture trouvée dans le CSV.")
            return

        # Fetch invoices in one query
        invoices = self.search([("name", "in", list(set(invoice_codes)))])
        invoices_map = {inv.name: inv for inv in invoices}

        _logger.info("Factures trouvées dans Odoo: %s / %s", len(invoices), len(set(invoice_codes)))

        for row in rows:
            name = (row[0] or "").strip()

            if name.startswith("FC") and len(name) > 2:
                name_odoo = name[:2] + "20" + name[2:]
            else:
                name_odoo = name

            sign = (row[2] or "").strip()
            amount_str = (row[3] or "").replace(",", ".").strip()

            _logger.warning("Facture CSV=%s => Odoo=%s | date=%s | sign=%s | montant=%s",
                            name, name_odoo, row[1], sign, amount_str)

            # Date paiement
            try:
                parsed_date = datetime.strptime((row[1] or "").strip(), "%d/%m/%Y").date()
                date_of_payment = fields.Date.to_string(parsed_date)
            except ValueError as e:
                _logger.error("Date invalide pour %s : %s (valeur=%s)", name_odoo, e, row[1])
                continue

            if not amount_str:
                _logger.warning("Montant vide pour %s, ligne ignorée.", name_odoo)
                continue

            try:
                amount = float(amount_str)
            except ValueError:
                _logger.warning("Montant non convertible pour %s : '%s'", name_odoo, amount_str)
                continue

            invoice = invoices_map.get(name_odoo)
            if not invoice:
                _logger.warning("Facture non trouvée dans Odoo: %s", name_odoo)
                continue

            # On ne traite que les lignes + (tu peux étendre si besoin)
            if sign != "+":
                _logger.info("Ligne ignorée (sign != '+') pour %s", name_odoo)
                continue

            try:
                # S'assurer que la facture est validée
                if invoice.state != "posted":
                    invoice.action_post()

                # Si déjà payée / rien à payer, on évite de créer un paiement en double
                if invoice.amount_residual == 0:
                    _logger.info("Facture déjà soldée: %s", invoice.name)
                    continue

                # Créer le paiement via wizard sur un journal de CAISSE => statut PAYÉ
                self._register_payment_paid(invoice, amount, date_of_payment)

                _logger.info("✅ Paiement enregistré pour la facture %s : %.2f €", name_odoo, amount)

            except Exception as e:
                _logger.error("❌ Échec paiement pour la facture %s : %s", name_odoo, e)

    # -------------------------
    # WIZARD PAIEMENT (STATUT PAYÉ)
    # -------------------------
    def _register_payment_paid(self, invoice, amount, date_of_payment):
        """
        Enregistre un paiement via account.payment.register sur un journal de CAISSE,
        pour obtenir paiement_state = paid directement (pas 'in_payment').
        """
        company = invoice.company_id

        cash_journal = self.env["account.journal"].search([
            ("type", "=", "cash"),
            ("code", "=", "CSH1"),              # <-- explicite, zéro doute
            ("company_id", "=", invoice.company_id.id),
        ], limit=1)
        
        if not cash_journal:
            raise UserError("Journal de caisse CSH1 (Espèces) introuvable.")

        payment_method_line = cash_journal.inbound_payment_method_line_ids[:1]
        if not payment_method_line:
            manual_payment_method = self.env.ref("account.account_payment_method_manual_in")
            payment_method_line = self.env["account.payment.method.line"].create({
                "name": "Manual In",
                "payment_method_id": manual_payment_method.id,
                "journal_id": cash_journal.id,
                "payment_type": "inbound",
            })
            _logger.warning("🔧 Mode de paiement ajouté au journal %s", cash_journal.name)

        PaymentRegister = self.env["account.payment.register"].with_context(
            active_model="account.move",
            active_ids=invoice.ids,
        )

        wizard = PaymentRegister.create({
            "payment_date": date_of_payment,
            "journal_id": cash_journal.id,
            "amount": amount,
            "payment_method_line_id": payment_method_line.id,
        })

        wizard.action_create_payments()
