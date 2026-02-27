import tempfile
import os
import shutil
import base64
import paramiko
import csv
import posixpath
from pathlib import Path
from datetime import datetime, date
from odoo import models, fields, api
from odoo.tools import html2plaintext
import logging

_logger = logging.getLogger(__name__)

class ExportSFTPScheduler(models.Model):
    _name = "export.sftp.scheduler"
    _description = "Export automatique vers SFTP"

    def _get_or_create_temp_dir(self):
        """Obtient ou crée le dossier temporaire persistant pour les exports."""
        ICP = self.env["ir.config_parameter"].sudo()
        temp_dir = ICP.get_param("export_powerbi.tmp_export_dir")

        if not temp_dir or not os.path.exists(temp_dir):
            # Créer un dossier persistant dans le répertoire des données Odoo
            base_dir = Path(self.env["ir.attachment"]._filestore())
            temp_dir = base_dir.parent / "export_powerbi_temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            ICP.set_param("export_powerbi.tmp_export_dir", str(temp_dir))
            _logger.info(f"[Export Power BI] Dossier temporaire créé : {temp_dir}")

        return temp_dir

    def _mkdir_p_sftp(self, sftp, remote_dir: str):
        """Crée récursivement les dossiers distants sur le serveur SFTP."""
        remote_dir = (remote_dir or "").strip().rstrip("/")
        if not remote_dir:
            return
        parts = [p for p in remote_dir.split("/") if p]
        cur = ""
        for p in parts:
            cur = f"{cur}/{p}" if cur else p
            try:
                sftp.stat(cur)
            except IOError:
                try:
                    sftp.mkdir(cur)
                    _logger.info(f"[SFTP] Dossier créé : {cur}")
                except Exception as e:
                    _logger.warning(f"[SFTP] Impossible de créer {cur} : {e}")

    @api.model
    def cron_generate_files(self):
        """Génère les fichiers Excel pour clients, commandes, factures, et les stocke en pièces jointes"""
        today = datetime.now().strftime("%Y%m%d")
        temp_dir = self._get_or_create_temp_dir()
        _logger.info(f"[Export Power BI] Dossier d'export : {temp_dir}")

        # helper pour formater un float d'heure (ex: 8.5) en '08:30'
        def _float_to_hhmm(val):
            try:
                if val is None or val == "":
                    return ""
                hours = int(val)
                minutes = int(round((val - hours) * 60))
                if minutes == 60:
                    hours += 1
                    minutes = 0
                return f"{hours:02d}:{minutes:02d}"
            except Exception:
                return val

        # helper M2O -> texte (safe)
        def _m2o_name(val):
            try:
                if not val:
                    return ""
                name = getattr(val, "name", None)
                if name is None:
                    return val
                return name or ""
            except Exception:
                return ""

        # Sanitize universel: convertit toute valeur en type "écrivible" par xlsxwriter
        def _to_cell(v):
            try:
                if v is None:
                    return ""
                if isinstance(v, (int, float, bool)):
                    return v
                if isinstance(v, str):
                    return v
                if isinstance(v, (datetime,)):
                    return v.strftime("%Y-%m-%d %H:%M:%S")
                if isinstance(v, (date,)):
                    return v.strftime("%Y-%m-%d")
                if isinstance(v, (bytes, bytearray)):
                    try:
                        return v.decode("utf-8", errors="ignore")
                    except Exception:
                        return str(v)
                try:
                    from odoo.models import BaseModel

                    if isinstance(v, BaseModel):
                        if not v:
                            return ""
                        if len(v) == 1:
                            return (
                                getattr(v, "display_name", None)
                                or getattr(v, "name", None)
                                or v.id
                            )
                        parts = []
                        for rec in v:
                            parts.append(
                                getattr(rec, "display_name", None)
                                or getattr(rec, "name", None)
                                or str(rec.id)
                            )
                        return ", ".join([str(p) for p in parts])
                except Exception:
                    pass
                if isinstance(v, (list, tuple, set, dict)):
                    try:
                        if isinstance(v, dict):
                            return str(v)
                        parts = [_to_cell(x) for x in v]
                        return ", ".join([str(p) for p in parts])
                    except Exception:
                        return str(v)
                return str(v)
            except Exception:
                return str(v)

        def write_csv(filename, headers, rows):
            filepath = os.path.join(temp_dir, filename)
            with open(filepath, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(headers)
                for row in rows:
                    writer.writerow([_to_cell(cell) for cell in row])
            _logger.info(f"[Export Power BI] Fichier créé : {filepath}")
            return filepath
        def to_float(value):
            try:
                return float(value or 0.0)
            except (TypeError, ValueError):
                return 0.0
        def create_attachment(filepath, name):
            with open(filepath, "rb") as f:
                file_content = f.read()
            self.env["ir.attachment"].create(
                {
                    "name": name,
                    "type": "binary",
                    "datas": base64.b64encode(file_content).decode(),
                    "res_model": "export.sftp.scheduler",
                    "res_id": 0,
                    "mimetype": "text/csv",
                }
            )
            _logger.info(f"[Export Power BI] Pièce jointe créée : {name}")

        try:
            # ==================== Clients ====================
            try:
                # clients = self.env["res.partner"].search([("customer_rank", ">", 0)])
                #clients = self.env["res.partner"].search([("sale_order_ids.state", "in", ["sale", "done","validated"])])
                clients = self.env["res.partner"].search([])
                client_data = [
                    (
                        str(p.id),
                        getattr(p, "company_type", "") or "",
                        p.parent_id.id or "",
                        p.parent_name or "",
                        p.name or "",
                        # bool(getattr(p, 'is_company', False)),
                        getattr(p, "x_studio_civilit_1", "") or "",
                        p.street or "",
                        getattr(p, "street2", "") or "",
                        p.city or "",
                        p.zip or "",
                        # (p.country_id.name if getattr(p, 'country_id', False) else ''),
                        p.phone or "",
                        getattr(p, "mobile", "") or "",
                        p.email or "",
                        p.vat or "",
                        _m2o_name(getattr(p, "x_studio_commercial_1", None))
                        or (getattr(p, "x_studio_commercial_1", "") or ""),
                        # getattr(p, 'x_studio_gneration_n_compte_1', '') or '',
                        getattr(p, "x_studio_compte", "") or "",
                        getattr(p, "x_studio_code_diap", "") or "",
                        getattr(p, "x_studio_mode_de_rglement_dsa", "") or "",
                        p.x_studio_mode_de_rglement_dsa.x_studio_libelle or "",
                        # bool(getattr(p, 'active', True)),
                        getattr(p, "html2plaintext(comment).strip()", "") or "",
                        p.siret or "",
                        getattr(p, "part_siren", "") or "",
                        getattr(p, "part_date_couverture", "") or "",
                        to_float(getattr(p, "part_montant_couverture", "") or ""),
                        to_float(getattr(p, "part_decision", "") or ""),
                        to_float(to_float(getattr(p, "part_encours_autoris", "") or "")),
                        to_float(getattr(p, "outstandings", "") or ""),
                        to_float(getattr(p, "x_studio_mtt_echu", "") or ""),
                        to_float(getattr(p, "x_studio_mtt_non_echu", "") or ""),
                        p.create_date.strftime("%Y-%m-%d %H:%M:%S")
                        if getattr(p, "create_date", False)
                        else "",
                        p.write_date.strftime("%Y-%m-%d %H:%M:%S")
                        if getattr(p, "write_date", False)
                        else "",
                        ", ".join([c.name for c in getattr(p, "category_id", [])])
                        if getattr(p, "category_id", False)
                        else "",
                    )
                    for p in clients
                ]
                client_file = write_csv(
                    f"clients.csv",
                    [
                        "ID Client",
                        "Type",
                        "Id Societe rattachee",
                        "Societe rattachee",
                        "Nom",
                        "Civilite",
                        "Rue",
                        "Rue 2",
                        "Ville",
                        "Code Postal",
                        "Telephone",
                        "Mobile",
                        "Email",
                        "TVA",
                        "Commercial",
                        "Compte_Progi",
                        "Code_Diap",
                        "Mode_de_reglement",
                        "Libelle",
                        "Commentaire",
                        "Siret",
                        "Siren",
                        "Date demande ND COVER ",
                        "Garantie Specifique",
                        "Encours Assure",
                        "Encours autorise",
                        "Encours",
                        "Mtt_Echu",
                        "Mtt_Non_Echu",
                        "Date_creation",
                        "Date_Modification",
                        "Catégorie",
                    ],
                    client_data,
                )
                create_attachment(client_file, os.path.basename(client_file))
                _logger.info("[Export Power BI] Clients: %s lignes", len(client_data))
            except Exception as e:
                _logger.exception("[Export Power BI] ERREUR section Clients: %s", e)

            # ==================== Commandes ====================
            try:
                orders = self.env["sale.order"].search([])
                order_data = [
                    (
                        str(o.id),
                        o.name or "",
                        o.state or "",
                        o.date_order.strftime("%Y-%m-%d %H:%M:%S")
                        if getattr(o, "date_order", False)
                        else "",
                        # getattr(o, 'validity_date', False) and o.validity_date.strftime('%Y-%m-%d') or '',
                        o.origin or "",
                        # getattr(o, 'client_order_ref', '') or '',
                        (
                            str(o.partner_id.id)
                            if getattr(o, "partner_id", False)
                            else ""
                        ),
                        (o.partner_id.name if getattr(o, "partner_id", False) else ""),
                        (
                            str(o.partner_invoice_id.id)
                            if getattr(o, "partner_invoice_id", False)
                            else ""
                        ),
                        (
                            o.partner_invoice_id.name
                            if getattr(o, "partner_invoice_id", False)
                            else ""
                        ),
                        (
                            str(o.partner_shipping_id.id)
                            if getattr(o, "partner_shipping_id", False)
                            else ""
                        ),
                        (
                            o.partner_shipping_id.name
                            if getattr(o, "partner_shipping_id", False)
                            else ""
                        ),
                        (str(o.user_id.id) if getattr(o, "user_id", False) else ""),
                        (o.user_id.name if getattr(o, "user_id", False) else ""),
                        # getattr(o, 'commitment_date', False) and o.commitment_date.strftime('%Y-%m-%d %H:%M:%S') or '',
                        (
                            o.currency_id.name
                            if getattr(o, "currency_id", False)
                            else ""
                        ),
                        (
                            o.payment_term_id.name
                            if getattr(o, "payment_term_id", False)
                            else ""
                        ),
                        to_float(getattr(o, "amount_untaxed", 0.0) or 0.0),
                        to_float(getattr(o, "amount_tax", 0.0) or 0.0),
                        to_float(getattr(o, "amount_total", 0.0) or 0.0),
                        o.invoice_status or "",
                        ", ".join([t.name for t in getattr(o, "tag_ids", [])])
                        if getattr(o, "tag_ids", False)
                        else "",
                        # getattr(o, 'confirmation_date', False) and o.confirmation_date.strftime('%Y-%m-%d %H:%M:%S') or '',
                        _m2o_name(getattr(o, "x_studio_commercial_1", None))
                        or (getattr(o, "x_studio_commercial_1", "") or ""),
                        _m2o_name(getattr(o, "x_studio_srie", None))
                        or (getattr(o, "x_studio_srie", "") or ""),
                        _m2o_name(getattr(o, "x_studio_gamme", None))
                        or (getattr(o, "x_studio_gamme", "") or ""),
                        getattr(o, "x_studio_avancement", "") or "",
                        _m2o_name(getattr(o, "x_studio_bureau_dtude", None))
                        or (getattr(o, "x_studio_bureau_dtude", "") or ""),
                        _m2o_name(getattr(o, "x_studio_projet", None))
                        or (getattr(o, "x_studio_projet", "") or ""),
                        getattr(o, "so_delai_confirme_en_semaine", "") or "",
                        getattr(o, "so_commande_client", "") or "",
                        _m2o_name(getattr(o, "x_studio_mode_de_rglement", None))
                        or (getattr(o, "x_studio_mode_de_rglement", "") or ""),
                        o.so_date_de_reception_devis.strftime("%Y-%m-%d")
                        if getattr(o, "so_date_de_reception_devis", False)
                        else "",
                        o.so_date_du_devis.strftime("%Y-%m-%d")
                        if getattr(o, "so_date_du_devis", False)
                        else "",
                        o.so_date_de_modification_devis.strftime("%Y-%m-%d")
                        if getattr(o, "so_date_de_modification_devis", False)
                        else "",
                        o.so_date_devis_valide.strftime("%Y-%m-%d")
                        if getattr(o, "so_date_devis_valide", False)
                        else "",
                        o.so_date_ARC.strftime("%Y-%m-%d")
                        if getattr(o, "so_date_ARC", False)
                        else "",
                        o.so_date_bpe.strftime("%Y-%m-%d")
                        if getattr(o, "so_date_bpe", False)
                        else "",
                        o.so_date_bon_pour_fab.strftime("%Y-%m-%d")
                        if getattr(o, "so_date_bon_pour_fab", False)
                        else "",
                        o.so_date_de_fin_de_production_reel.strftime("%Y-%m-%d")
                        if getattr(o, "so_date_de_fin_de_production_reel", False)
                        else "",
                        o.so_date_de_livraison.strftime("%Y-%m-%d")
                        if getattr(o, "so_date_de_livraison", False)
                        else "",
                        o.so_date_de_livraison_prevu.strftime("%Y-%m-%d")
                        if getattr(o, "so_date_de_livraison_prevu", False)
                        else "",
                        to_float(getattr(o, "so_achat_matiere_devis", 0.0) or 0.0),
                        to_float(getattr(o, "so_achat_vitrage_devis", 0.0) or 0.0),
                        to_float(getattr(o, "so_cout_mod_devis", 0.0) or 0.0),
                        to_float(getattr(o, "so_mtt_facturer_devis", 0.0) or 0.0),
                        to_float(getattr(o, "so_marge_brute_devis", 0.0) or 0.0),
                        to_float(getattr(o, "so_mcv_devis", 0.0) or 0.0),
                        to_float(getattr(o, "so_achat_matiere_be", 0.0) or 0.0),
                        to_float(getattr(o, "so_achat_vitrage_be", 0.0) or 0.0),
                        to_float(getattr(o, "so_cout_mod_be", 0.0) or 0.0),
                        to_float(getattr(o, "so_mtt_facturer_be", 0.0) or 0.0),
                        to_float(getattr(o, "so_marge_brute_be", 0.0) or 0.0),
                        to_float(getattr(o, "so_mcv_be", 0.0) or 0.0),
                        to_float(getattr(o, "so_achat_matiere_reel", 0.0) or 0.0),
                        to_float(getattr(o, "so_achat_vitrage_reel", 0.0) or 0.0),
                        to_float(getattr(o, "so_cout_mod_reel", 0.0) or 0.0),
                        to_float(getattr(o, "so_mtt_facturer_reel", 0.0) or 0.0),
                        to_float(getattr(o, "so_marge_brute_reel", 0.0) or 0.0),
                        to_float(getattr(o, "so_mcv_reel", 0.0) or 0.0),
                        to_float(getattr(o, "x_studio_so_cout_appro_affaire", 0.0) or 0.0),
                        to_float(getattr(o, "x_studio_so_cout_appro_stock", 0.0) or 0.0),
                    )
                    for o in orders
                ]
                order_file = write_csv(
                    f"commandes.csv",
                    [
                        "ID Commande",
                        "Num Commande",
                        "Etat",
                        "Date Creation Devis (ODOO)",
                        "Origine",
                        "ID Client",
                        "Client",
                        "ID Facturation",
                        "Adresse Facturation",
                        "ID Livraison",
                        "Adresse Livraison",
                        "ID BEC Ventes ",
                        "BEC Ventes",
                        "Devise",
                        "Conditions de paiement",
                        "Mtt_HT",
                        "TVA",
                        "Mtt_TTC",
                        "Statut_facturation",
                        "Tags",
                        "Commercial",
                        "Serie",
                        "Gamme",
                        "Avancement",
                        "BET Méthodes",
                        "Projet",
                        "Delai confirmé en semaine",
                        "Commande client",
                        "Mode de reglement",
                        "Date recep demande devis",
                        "Date creation devis",
                        "Derniere Date modif devis",
                        "Date validation devis par le client",
                        "Date envoi ARC",
                        "Date BPE",
                        "Date debut de fab",
                        "Date fin de fab",
                        "Date de livraison prévue",
                        "Date de livraison reelle",
                        "Achat Matiere Devis",
                        "Achat Vitrage Devis",
                        "Cout MOD Devis",
                        "Marge Brute Devis",
                        "MCV Devis",
                        "Achat Matiere BE",
                        "Achat Vitrage BE",
                        "Cout MOD BE",
                        "Marge Brute BE",
                        "MCV BE",
                        "Achat Matiere Reel",
                        "Achat Vitrage Reel",
                        "Cout MOD Reel",
                        "Marge Brute Reel",
                        "MCV Reel",
                        "Achat affaire Reel",
                        "Achat stock Reel",
                    ],
                    order_data,
                )
                create_attachment(order_file, os.path.basename(order_file))
                _logger.info("[Export Power BI] Commandes: %s lignes", len(order_data))
            except Exception as e:
                _logger.exception("[Export Power BI] ERREUR section Commandes: %s", e)

            # Les autres sections suivent le même pattern...
            # (Lignes de commandes, Factures, Lignes de factures)
            # Je les ai omises pour la concision, mais elles fonctionnent de la même manière
            # =========================================================
            # Lignes de commandes (sale.order.line)
            # =========================================================
            order_lines = self.env["sale.order.line"].search(
                [("product_id", "!=", False)]
            )
            order_line_data = [
                (
                    str(l.id),
                    getattr(l, "sequence", 10),
                    # Lien commande
                    (str(l.order_id.id) if getattr(l, "order_id", False) else ""),
                    (l.order_id.name if getattr(l, "order_id", False) else ""),
                    (
                        l.order_id.x_studio_projet
                        if getattr(l, "order_id", False)
                        else ""
                    ),
                    # Tags (sur la commande)
                    ", ".join([t.name for t in (l.order_id.tag_ids or [])]) if l.order_id else "",
                    (l.order_id.state if getattr(l, "order_id", False) else ""),
                    (
                        l.order_id.date_order.strftime("%Y-%m-%d %H:%M:%S")
                        if (
                            getattr(l, "order_id", False)
                            and getattr(l.order_id, "date_order", False)
                        )
                        else ""
                    ),
                    # Client
                    (
                        str(l.order_id.partner_id.id)
                        if (
                            getattr(l, "order_id", False)
                            and getattr(l.order_id, "partner_id", False)
                        )
                        else ""
                    ),
                    (
                        l.order_id.partner_id.name
                        if (
                            getattr(l, "order_id", False)
                            and getattr(l.order_id, "partner_id", False)
                        )
                        else ""
                    ),
                    # Produit
                    (str(l.product_id.id) if getattr(l, "product_id", False) else ""),
                    (
                        l.product_id.default_code
                        if getattr(l, "product_id", False)
                        else ""
                    )
                    or "",
                    (l.product_id.name if getattr(l, "product_id", False) else "")
                    or "",
                    (
                        l.product_id.categ_id.name
                        if (
                            getattr(l, "product_id", False)
                            and getattr(l.product_id, "categ_id", False)
                        )
                        else ""
                    )
                    or "",
                    # Quantités / UoM / lead time
                    to_float(getattr(l, "product_uom_qty", 0.0) or 0.0),
                    to_float(getattr(l, "qty_delivered", 0.0) or 0.0),
                    to_float(getattr(l, "qty_invoiced", 0.0) or 0.0),
                    (l.product_uom.name if getattr(l, "product_uom", False) else ""),
                    # Prix / taxes / totaux
                    to_float(getattr(l, "price_unit", 0.0) or 0.0),
                    to_float(getattr(l, "discount", 0.0) or 0.0),
                    to_float((
                        (getattr(l, "price_unit", 0.0) or 0.0)
                        * (1 - (getattr(l, "discount", 0.0) or 0.0) / 100.0)
                    )),
                    ", ".join([t.name for t in getattr(l, "tax_id", [])])
                    if getattr(l, "tax_id", False)
                    else "",
                    to_float(getattr(l, "price_subtotal", 0.0) or 0.0),
                    to_float(getattr(l, "price_tax", 0.0) or 0.0),
                    to_float(getattr(l, "price_total", 0.0) or 0.0),
                    # Devise / société / vendeur
                    (l.currency_id.name if getattr(l, "currency_id", False) else ""),
                    # (l.company_id.name if getattr(l, 'company_id', False) else ''),
                    # (l.order_id.user_id.name if (getattr(l, 'order_id', False) and getattr(l.order_id, 'user_id', False)) else ''),
                )
                for l in order_lines
            ]
            order_line_file = write_csv(
                f"lignes_commandes.csv",
                [
                    "ID Ligne",
                    "Ordre affichage",
                    "ID Commande",
                    "Num Commande",
                    "Affaire",
                    "Tag",
                    "Etat_commande",
                    "Date_commande",
                    "ID Client",
                    "Client",
                    "ID Article",
                    "Code article",
                    "Nom article",
                    "Categorie_article",
                    "Qte Cde",
                    "Qte Liv",
                    "Qte Fact",
                    "Unite de Mesure",
                    "PU HT",
                    "Pourcentage Remise",
                    "Prix Unitaire Remise",
                    "Taxes",
                    "Mtt_Tot_HT",
                    "TVA",
                    "Mtt_Tot_TTC",
                    "Devise",
                ],
                order_line_data,
            )
            create_attachment(order_line_file, os.path.basename(order_line_file))
            # =========================================================
            # Factures (account.move - ventes postées)
            #   - Exclure les factures 100% acomptes
            #   - Garder les mixtes et ajouter HT sans acomptes
            # =========================================================
            try:
                invoices = self.env["account.move"].search(
                    [
                        ("state", "=", "posted"),
                        ("move_type", "in", ["out_invoice", "out_refund"]),
                        (
                            "invoice_line_ids.product_id.default_code",
                            "not ilike",
                            "ACPT",
                        ),
                        ("id", "!=", "9594"),
                    ]
                )

                invoice_data = [
                    (
                        str(i.id),
                        i.name or "",
                        getattr(i, "move_type", "") or "",
                        i.invoice_date.strftime("%Y-%m-%d")
                        if getattr(i, "invoice_date", False)
                        else "",
                        i.invoice_date_due.strftime("%Y-%m-%d")
                        if getattr(i, "invoice_date_due", False)
                        else "",
                        getattr(i, "invoice_origin", "") or "",
                        # Etat paiement
                        i.payment_state or "",
                        # Partenaire
                        (
                            str(i.partner_id.id)
                            if getattr(i, "partner_id", False)
                            else ""
                        ),
                        (i.partner_id.name if getattr(i, "partner_id", False) else ""),
                        # Organisation
                        (
                            i.currency_id.name
                            if getattr(i, "currency_id", False)
                            else ""
                        ),
                        (
                            i.invoice_payment_term_id.name
                            if getattr(i, "invoice_payment_term_id", False)
                            else ""
                        ),
                        i.x_studio_mode_de_reglement_1 or "",
                        i.x_studio_libelle_1 or "",
                        (
                            i.fiscal_position_id.name
                            if getattr(i, "fiscal_position_id", False)
                            else ""
                        ),
                        # Montants
                        to_float(getattr(i, "amount_residual", 0.0) or 0.0),
                        to_float(getattr(i, "amount_untaxed_signed", 0.0)
                        or 0.0),  # HT signé "normal" (inclut acomptes)
                        to_float(getattr(i, "amount_total_signed", 0.0) or 0.0),
                        # Divers
                        getattr(i, "x_studio_projet_vente", 0.0) or 0.0,
                        getattr(i, "inv_activite", None) or 'COMMUN',
                        len(getattr(i, "invoice_line_ids", [])),
                    )
                    for i in invoices
                ]

                invoice_file = write_csv(
                    f"factures.csv",
                    [
                        "ID Facture",
                        "Numero de Facture",
                        "Type",
                        "Date Facture",
                        "Echeance",
                        "Origine",
                        "Etat_Paiement",
                        "ID Client",
                        "Client",
                        "Devise",
                        "Condition de paiement",
                        "Mode de reglement",
                        "Libelle mode de reglement",
                        "Position_fiscale",
                        "Mtt_du",
                        "Mtt_HT",
                        "Mtt_TTC",
                        "Affaire",
                        "Activite",
                        "Nb_lignes",
                    ],
                    invoice_data,
                )
                create_attachment(invoice_file, os.path.basename(invoice_file))
                _logger.info("[Export Power BI] Factures: %s lignes", len(invoice_data))

            except Exception as e:
                _logger.exception("[Export Power BI] ERREUR section Factures: %s", e)

            try:
                # =========================================================
                # Lignes de factures (account.move.line)
                # =========================================================
                invoice_lines = self.env["account.move.line"].search(
                    [
                        ("move_id.move_type", "in", ["out_invoice", "out_refund"]),
                        ("move_id.state", "=", "posted"),
                        ("product_id", "!=", False),
                        ("move_id.id", "!=", "9594"),
                    ]
                )
                invoice_line_data = [
                    (
                        str(l.id),
                        getattr(l, "sequence", 10),
                        # Move / facture
                        (str(l.move_id.id) if getattr(l, "move_id", False) else ""),
                        (l.move_id.name if getattr(l, "move_id", False) else ""),
                        (
                            l.move_id.invoice_date.strftime("%Y-%m-%d")
                            if (
                                getattr(l, "move_id", False)
                                and getattr(l.move_id, "invoice_date", False)
                            )
                            else ""
                        ),
                        (
                            str(l.move_id.partner_id.id)
                            if (
                                getattr(l, "move_id", False)
                                and getattr(l.move_id, "partner_id", False)
                            )
                            else ""
                        ),
                        (
                            l.move_id.partner_id.name
                            if (
                                getattr(l, "move_id", False)
                                and getattr(l.move_id, "partner_id", False)
                            )
                            else ""
                        ),
                        # Ligne
                        getattr(l, "name", "") or "",
                        (getattr(l, "display_type", "") or ""),
                        # Produit
                        (
                            str(l.product_id.id)
                            if getattr(l, "product_id", False)
                            else ""
                        ),
                        (
                            l.product_id.default_code
                            if getattr(l, "product_id", False)
                            else ""
                        )
                        or "",
                        (l.product_id.name if getattr(l, "product_id", False) else "")
                        or "",
                        (
                            l.product_id.categ_id.name
                            if (
                                getattr(l, "product_id", False)
                                and getattr(l.product_id, "categ_id", False)
                            )
                            else ""
                        )
                        or "",
                        # Quantité / UoM
                        to_float(getattr(l, "quantity", 0.0) or 0.0),
                        (
                            getattr(l, "product_uom_id", False)
                            and l.product_uom_id.name
                            or ""
                        ),
                        # Prix / taxes / totaux (facture-line API)
                        # Négatif si avoir (out_refund)
                        to_float((getattr(l, "price_unit", 0.0) or 0.0) * (-1 if l.move_id.move_type == "out_refund" else 1)),
                        ", ".join([t.name for t in getattr(l, "tax_ids", [])])
                        if getattr(l, "tax_ids", False)
                        else "",
                        to_float((getattr(l, "price_subtotal", 0.0) or 0.0) * (-1 if l.move_id.move_type == "out_refund" else 1)),
                        to_float((getattr(l, "price_total", 0.0) or 0.0) * (-1 if l.move_id.move_type == "out_refund" else 1)),
                        (
                            l.currency_id.name
                            if getattr(l, "currency_id", False)
                            else ""
                        ),
                        # Comptabilité
                        (l.account_id.code if getattr(l, "account_id", False) else ""),
                        (l.account_id.name if getattr(l, "account_id", False) else ""),
                        # getattr(l, 'debit', 0.0) or 0.0,
                        # getattr(l, 'credit', 0.0) or 0.0,
                        # getattr(l, 'balance', 0.0) or 0.0,
                        # getattr(l, 'amount_currency', 0.0) or 0.0,
                        # Analytique
                        (
                            l.analytic_account_id.name
                            if getattr(l, "analytic_account_id", False)
                            else ""
                        ),
                        ", ".join([t.name for t in getattr(l, "analytic_tag_ids", [])])
                        if getattr(l, "analytic_tag_ids", False)
                        else "",
                        # Lien vente
                        (
                            str(l.sale_line_ids[0].id)
                            if getattr(l, "sale_line_ids", False) and l.sale_line_ids
                            else ""
                        ),
                        # Flag acompte
                        "Oui"
                        if (
                            getattr(l, "product_id", False)
                            and getattr(l.product_id, "default_code", False)
                            and "cpt" in str(l.product_id.default_code).lower()
                        )
                        else "Non",
                    )
                    for l in invoice_lines
                ]
                invoice_line_file = write_csv(
                    f"lignes_factures.csv",
                    [
                        "ID Ligne",
                        "Sequence",
                        "ID Facture",
                        "NumFac",
                        "Date_facture",
                        "ID Client",
                        "Client",
                        "Libelle",
                        "Type_affichage",
                        "ID Article",
                        "Code_article",
                        "Nom_article",
                        "Categorie_article",
                        "Qte",
                        "UoM",
                        "PU_HT",
                        "Taxes",
                        "Mtt_HT",
                        "Mtt_TTC",
                        "Devise",
                        "Compte_code",
                        "Compte_libelle",
                        "Compte_Analytique",
                        "Tags_analytiques",
                        "ID Ligne_Commande",
                        "Ligne acompte",
                    ],
                    invoice_line_data,
                )
                create_attachment(
                    invoice_line_file, os.path.basename(invoice_line_file)
                )
                _logger.info(
                    "[Export Power BI] Lignes de factures: %s lignes",
                    len(invoice_line_data),
                )

            except Exception as e:
                _logger.exception(
                    "[Export Power BI] ERREUR section Lignes de factures: %s", e
                )
            # =========================================================
            # Notes factures (mail.message)
            #   - Notes du chatter liées aux factures (account.move)
            # =========================================================
            try:
                invoice_ids = invoices.ids  # les factures déjà récupérées plus haut
            
                messages = self.env["mail.message"].search(
                    [
                        ("model", "=", "account.move"),
                        ("res_id", "in", invoice_ids),
                        ("message_type", "=", "comment"),  # chatter "commentaires"
                        # Optionnel: si tu veux uniquement les "Notes internes"
                        # ("subtype_id.internal", "=", True),
                    ],
                    order="date asc",
                )
            
                notes_data = [
                    (
                        str(m.id),
                        str(m.res_id),  # ID facture
                        m.date.strftime("%Y-%m-%d %H:%M:%S") if m.date else "",
                        (m.author_id.name if m.author_id else ""),
                        # body est HTML -> on peut le laisser tel quel ou nettoyer
                        (m.body or "").replace("\n", " ").strip(),
                    )
                    for m in messages
                ]
            
                notes_file = write_csv(
                    "factures_notes.csv",
                    ["ID Message", "ID Facture", "Date", "Auteur", "Note (HTML)"],
                    notes_data,
                )
                create_attachment(notes_file, os.path.basename(notes_file))
                _logger.info("[Export Power BI] Notes factures: %s lignes", len(notes_data))
            
            except Exception as e:
                _logger.exception("[Export Power BI] ERREUR section Notes factures: %s", e)
                
            # ========================================
            # Commande Appro (purchase.order)
            # ==========================================
            try:
                purchases = self.env["purchase.order"].search([])
                purchase_data = [
                    (
                        j.id,
                        j.name or "",
                        j.partner_id.id or "",
                        j.partner_id.name or "",
                        getattr(j, "x_studio_projet_du_so", "") or "",
                        getattr(j, "x_studio_commentaire_interne_", "") or "",
                        getattr(j, "x_studio_rfrence", "") or "",
                        j.create_date.strftime("%Y-%m-%d %H:%M:%S")
                        if getattr(j, "create_date", False)
                        else "",
                        j.date_planned.strftime("%Y-%m-%d %H:%M:%S")
                        if getattr(j, "date_planned", False)
                        else "",
                        j.picking_type_id or "",
                        j.x_studio_remise_1 or "",
                    )
                    for j in purchases
                ]
                purchase_file = write_csv(
                    f"OA.csv",
                    [
                        "ID",
                        "Nom",
                        "ID_Fournisseur",
                        "Fournisseur",
                        "Affaire",
                        "Commentaire_Interne",
                        "Reference",
                        "Date_cree",
                        "Date_Liv_Prev",
                        "Entrepot",
                        "Remise",
                    ],
                    purchase_data,
                )
                create_attachment(purchase_file, os.path.basename(purchase_file))
            except Exception as e:
                _logger.exception(
                    "[Export Power BI] ERREUR section Commande Appro: %s", e
                )

            try:
                # ========================================
                # Commande Ligne Appro (purchase.order.line)
                # ==========================================
                line_purchases = self.env["purchase.order.line"].search([])
                line_purchase_data = [
                    (
                        i.id,
                        i.name or "",
                        # Produit
                        (i.product_id.id if getattr(i, "product_id", False) else ""),
                        (
                            i.product_id.default_code
                            if getattr(i, "product_id", False)
                            else ""
                        )
                        or "",
                        (i.product_id.name if getattr(i, "product_id", False) else "")
                        or "",
                        (
                            i.product_id.categ_id.name
                            if (
                                getattr(i, "product_id", False)
                                and getattr(i.product_id, "categ_id", False)
                            )
                            else ""
                        )
                        or "",
                        # Quantité / UoM
                        getattr(i, "product_qty", 0.0) or 0.0,
                        getattr(i, "qty_received", 0.0) or 0.0,
                        getattr(i, "qty_invoiced", 0.0) or 0.0,
                        (
                            getattr(i, "product_uom_id", False)
                            and i.product_uom_id.name
                            or ""
                        ),
                        # Prix / taxes / totaux (facture-line API)
                        getattr(i, "price_unit", 0.0) or 0.0,
                        ", ".join([t.name for t in getattr(i, "tax_ids", [])])
                        if getattr(i, "tax_ids", False)
                        else "",
                        getattr(i, "price_subtotal", 0.0) or 0.0,
                        getattr(i, "price_total", 0.0) or 0.0,
                        (
                            i.currency_id.name
                            if getattr(i, "currency_id", False)
                            else ""
                        ),
                        # Comptabilité
                        # (l.account_id.code if getattr(l, 'account_id', False) else ''),
                        # (l.account_id.name if getattr(l, 'account_id', False) else ''),
                    )
                    for i in line_purchases
                ]
                line_purchase_file = write_csv(
                    f"ligne_OA.csv",
                    [
                        "ID",
                        "Nom",
                        "ID_Produit",
                        "Ref_Produit",
                        "Produit",
                        "Categorie",
                        "Qte_Cde",
                        "Qte_Rec",
                        "Qte_Fac",
                        "Unit_Mes",
                        "Mtt_Unit",
                        "TVA",
                        "Mtt_Sst",
                        "Mtt_Tot",
                        "Devise",
                    ],
                    line_purchase_data,
                )
                create_attachment(
                    line_purchase_file, os.path.basename(line_purchase_file)
                )
            except Exception as e:
                _logger.exception("[Export Power BI] ERREUR section Ligne Appro: %s", e)
        except Exception as e:
            _logger.exception(
                "Erreur globale lors de la génération des fichiers Power BI : %s", e
            )

    @api.model
    def cron_send_files_to_sftp(self):
        """Envoie les fichiers Excel/CSV générés vers le serveur SFTP."""

        # 🔐 Paramètres SFTP - À ADAPTER AVEC VOS VALEURS SÉCURISÉES
        ICP = self.env["ir.config_parameter"].sudo()
        host = ICP.get_param("export_powerbi.sftp_host", "194.206.49.72")
        port = int(ICP.get_param("export_powerbi.sftp_port", "22"))
        username = ICP.get_param("export_powerbi.sftp_username", "csproginov")
        password = ICP.get_param("export_powerbi.sftp_password", "g%tumR/n49:1=5qES6CT")
        remote_path = ICP.get_param(
            "export_powerbi.sftp_remote_path", "FMA/OUT/POWERBI/"
        )

        # 🛑 Vérification paramètres
        if not all([host, username, remote_path, password]):
            _logger.error("❌ Paramètres SFTP manquants ou incomplets.")
            return

        # 📁 Récupération du dossier temporaire
        temp_dir = Path(self._get_or_create_temp_dir())

        # 📂 Vérification du dossier
        if not temp_dir.exists():
            _logger.error("❌ Le dossier temporaire n'existe pas : %s", temp_dir)
            return

        if not os.access(str(temp_dir), os.R_OK):
            _logger.error("❌ Pas de droits de lecture sur : %s", temp_dir)
            return

        # 📋 Liste des fichiers à envoyer
        files_to_send = [
            f for f in temp_dir.iterdir() if f.is_file() and f.suffix in [".csv"]
        ]

        if not files_to_send:
            _logger.info("ℹ️ Aucun fichier à envoyer depuis %s.", temp_dir)
            return

        _logger.info("[SFTP] %s fichier(s) trouvé(s) à envoyer.", len(files_to_send))

        # 🔌 Connexion SFTP
        transport = None
        sftp = None
        try:
            transport = paramiko.Transport((host, port))
            transport.connect(username=username, password=password)
            sftp = paramiko.SFTPClient.from_transport(transport)
            _logger.info("✅ Connexion SFTP réussie à %s:%s", host, port)

            # 📁 Crée le dossier distant si besoin
            self._mkdir_p_sftp(sftp, remote_path)

            # 📤 Envoi des fichiers
            sent = 0
            for file_path in files_to_send:
                try:
                    remote_file = posixpath.join(
                        remote_path.rstrip("/"), file_path.name
                    )
                    sftp.put(str(file_path), remote_file)
                    _logger.info(
                        "📤 Fichier envoyé : %s -> %s", file_path.name, remote_file
                    )
                    sent += 1

                    # ✅ Supprime le fichier local après envoi réussi
                    try:
                        file_path.unlink()
                        _logger.info("🗑️ Fichier local supprimé : %s", file_path.name)
                    except Exception as e:
                        _logger.warning(
                            "⚠️ Impossible de supprimer %s : %s", file_path.name, e
                        )

                except Exception as e:
                    _logger.exception(
                        "❌ Erreur lors de l'envoi de %s : %s", file_path.name, e
                    )

            _logger.info(
                "✅ %s fichier(s) envoyé(s) avec succès vers %s", sent, remote_path
            )

        except paramiko.AuthenticationException:
            _logger.error(
                "❌ Échec d'authentification SFTP. Vérifiez username/password."
            )
        except paramiko.SSHException as e:
            _logger.exception("❌ Erreur SSH lors de la connexion SFTP : %s", e)
        except Exception as e:
            _logger.exception(
                "❌ Erreur lors de l'envoi des fichiers vers le SFTP : %s", e
            )
        finally:
            # 🔌 Ferme proprement la connexion
            try:
                if sftp:
                    sftp.close()
                if transport:
                    transport.close()
                _logger.info("[SFTP] Connexion fermée.")
            except Exception as e:
                _logger.warning("⚠️ Erreur lors de la fermeture SFTP : %s", e)
