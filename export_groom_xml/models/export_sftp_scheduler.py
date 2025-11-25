# -*- coding: utf-8 -*-
import os
import base64
import logging
import paramiko
import posixpath
import re
import xml.etree.ElementTree as ET

from pathlib import Path
from datetime import datetime, date

from odoo import models, api
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)


class ExportSFTPScheduler(models.Model):
    _name = 'export.sftp.scheduler'
    _description = 'Export automatique vers SFTP (XML)'

    # ---------------------------------------------------------
    # Utils fichiers & SFTP
    # ---------------------------------------------------------

    def _get_or_create_temp_dir(self):
        """Obtient ou crée le dossier temporaire persistant pour les exports."""
        ICP = self.env['ir.config_parameter'].sudo()
        temp_dir = ICP.get_param('export_groom.tmp_export_dir')

        if not temp_dir or not os.path.exists(temp_dir):
            base_dir = Path(self.env['ir.attachment']._filestore())
            temp_dir = base_dir.parent / 'export_powerbi_temp'
            temp_dir.mkdir(parents=True, exist_ok=True)
            ICP.set_param('export_groom.tmp_export_dir', str(temp_dir))
            _logger.info(f"[Export Groom] Dossier temporaire créé : {temp_dir}")

        return str(temp_dir)

    def _mkdir_p_sftp(self, sftp, remote_dir: str):
        """Crée récursivement les dossiers distants sur le serveur SFTP."""
        remote_dir = (remote_dir or "").strip().rstrip('/')
        if not remote_dir:
            return
        parts = [p for p in remote_dir.split('/') if p]
        cur = ''
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

    # ---------------------------------------------------------
    # Helpers de transformation
    # ---------------------------------------------------------

    def _float_to_hhmm(self, val):
        """Ex 8.5 -> '08:30'."""
        try:
            if val is None or val == '':
                return ''
            hours = int(val)
            minutes = int(round((val - hours) * 60))
            if minutes == 60:
                hours += 1
                minutes = 0
            return f"{hours:02d}:{minutes:02d}"
        except Exception:
            return val

    def _m2o_name(self, val):
        """M2O -> texte safe."""
        try:
            if not val:
                return ''
            name = getattr(val, 'name', None)
            if name is None:
                return val
            return name or ''
        except Exception:
            return ''

    def _to_cell(self, v):
        """Sanitize universel: convertit toute valeur en texte 'écrivible'."""
        try:
            if v is None:
                return ''
            if isinstance(v, (int, float, bool)):
                return v
            if isinstance(v, str):
                return v
            if isinstance(v, datetime):
                return v.strftime('%Y-%m-%d %H:%M:%S')
            if isinstance(v, date):
                return v.strftime('%Y-%m-%d')
            if isinstance(v, (bytes, bytearray)):
                try:
                    return v.decode('utf-8', errors='ignore')
                except Exception:
                    return str(v)

            try:
                from odoo.models import BaseModel
                if isinstance(v, BaseModel):
                    if not v:
                        return ''
                    if len(v) == 1:
                        return getattr(v, 'display_name', None) or getattr(v, 'name', None) or v.id
                    parts = []
                    for rec in v:
                        parts.append(
                            getattr(rec, 'display_name', None)
                            or getattr(rec, 'name', None)
                            or str(rec.id)
                        )
                    return ', '.join([str(p) for p in parts])
            except Exception:
                pass

            if isinstance(v, (list, tuple, set, dict)):
                try:
                    if isinstance(v, dict):
                        return str(v)
                    parts = [self._to_cell(x) for x in v]
                    return ', '.join([str(p) for p in parts])
                except Exception:
                    return str(v)

            return str(v)
        except Exception:
            return str(v)

    def _sanitize_tag(self, header):
        """
        Transforme un libellé de colonne en nom de balise XML valide.
        Ex: 'ID Client' -> 'id_client'
        """
        if not header:
            return 'field'
        tag = header.lower()
        tag = re.sub(r'[^a-z0-9]+', '_', tag)
        tag = tag.strip('_')
        return tag or 'field'

    def _write_xml(self, temp_dir, filename, root_tag, row_tag, headers, rows):
        """
        Écrit un fichier XML générique.
        root_tag: ex 'clients'
        row_tag : ex 'client'
        headers : liste des noms de colonnes
        rows    : liste de tuples/lists de valeurs
        """
        filepath = os.path.join(temp_dir, filename)
        root = ET.Element(root_tag)

        tag_names = [self._sanitize_tag(h) for h in headers]

        for row in rows:
            rec_el = ET.SubElement(root, row_tag)
            for header, tag_name, cell in zip(headers, tag_names, row):
                field_el = ET.SubElement(rec_el, tag_name)
                field_el.set('label', header)
                val = self._to_cell(cell)
                field_el.text = '' if val is None else str(val)

        tree = ET.ElementTree(root)
        tree.write(filepath, encoding='utf-8', xml_declaration=True)
        _logger.info(f"[Export Groom] Fichier XML créé : {filepath}")
        return filepath

    def _create_attachment(self, filepath, name, mimetype='application/xml'):
        with open(filepath, 'rb') as f:
            file_content = f.read()
        self.env['ir.attachment'].create({
            'name': name,
            'type': 'binary',
            'datas': base64.b64encode(file_content).decode(),
            'res_model': 'export.sftp.scheduler',
            'res_id': 0,
            'mimetype': mimetype,
        })
        _logger.info(f"[Export Groom] Pièce jointe créée : {name}")

    # ---------------------------------------------------------
    # CRON : génération des fichiers XML
    # ---------------------------------------------------------

    @api.model
    def cron_generate_files(self):
        """Génère les fichiers XML pour clients, commandes, factures, etc."""
        today = datetime.now().strftime('%Y%m%d')
        temp_dir = self._get_or_create_temp_dir()
        _logger.info(f"[Export Groom] Dossier d'export : {temp_dir}")

        try:
            # ==================== Clients ====================
            try:
                clients = self.env['res.partner'].search([('customer_rank', '>', 0)])
                client_data = [(
                    str(p.id),
                    getattr(p, 'company_type', '') or '',
                    p.parent_id.id or '',
                    p.parent_name or '',
                    p.name or '',
                    getattr(p, 'x_studio_civilit_1', '') or '',
                    p.street or '',
                    getattr(p, 'street2', '') or '',
                    p.city or '',
                    p.zip or '',
                    p.phone or '',
                    getattr(p, 'mobile', '') or '',
                    p.email or '',
                    p.vat or '',
                    self._m2o_name(getattr(p, 'x_studio_commercial_1', None)) or (getattr(p, 'x_studio_commercial_1', '') or ''),
                    getattr(p, 'x_studio_compte', '') or '',
                    getattr(p, 'x_studio_code_diap', '') or '',
                    getattr(p, 'x_studio_mode_de_rglement_dsa', '') or '',
                    p.x_studio_mode_de_rglement_dsa.x_studio_libelle or '',
                    html2plaintext(p.comment or '').strip() if getattr(p, 'comment', False) else '',
                    p.siret or '',
                    getattr(p, 'part_siren', '') or '',
                    getattr(p, 'part_date_couverture', '') or '',
                    getattr(p, 'part_montant_couverture', '') or '',
                    getattr(p, 'part_decision', '') or '',
                    getattr(p, 'part_encours_autoris', '') or '',
                    getattr(p, 'outstandings', '') or '',
                    getattr(p, 'x_studio_mtt_echu', '') or '',
                    getattr(p, 'x_studio_mtt_non_echu', '') or '',
                    p.create_date.strftime('%Y-%m-%d %H:%M:%S') if getattr(p, 'create_date', False) else '',
                    p.write_date.strftime('%Y-%m-%d %H:%M:%S') if getattr(p, 'write_date', False) else '',
                    ', '.join([c.name for c in getattr(p, 'category_id', [])]) if getattr(p, 'category_id', False) else '',
                ) for p in clients]

                client_headers = [
                    'ID Client','Type','Id Société rattachee','Societe rattachee','Nom',
                    'Civilite','Rue','Rue 2','Ville','Code Postal',
                    'Telephone','Mobile','Email',
                    'TVA','Commercial','Compte_Progi','Code_Diap','Mode_de_reglement','Libelle','Commentaire',
                    'Siret','Siren','Date demande ND COVER ','Garantie Specifique','Encours Assure','Encours autorise',
                    'Encours','Mtt_Echu','Mtt_Non_Echu','Date_creation','Date_Modification',
                    'Catégorie'
                ]

                client_file = self._write_xml(
                    temp_dir,
                    'clients.xml',
                    root_tag='clients',
                    row_tag='client',
                    headers=client_headers,
                    rows=client_data,
                )
                self._create_attachment(client_file, os.path.basename(client_file))
                _logger.info("[Export Groom] Clients: %s lignes", len(client_data))
            except Exception as e:
                _logger.exception("[Export Groom] ERREUR section Clients: %s", e)

            # ==================== Commandes ====================
            try:
                orders = self.env['sale.order'].search([])
                order_data = [(
                    str(o.id),
                    o.name or '',
                    o.state or '',
                    o.date_order.strftime('%Y-%m-%d %H:%M:%S') if getattr(o, 'date_order', False) else '',
                    o.origin or '',
                    (str(o.partner_id.id) if getattr(o, 'partner_id', False) else ''),
                    (o.partner_id.name if getattr(o, 'partner_id', False) else ''),
                    (str(o.partner_invoice_id.id) if getattr(o, 'partner_invoice_id', False) else ''),
                    (o.partner_invoice_id.name if getattr(o, 'partner_invoice_id', False) else ''),
                    (str(o.partner_shipping_id.id) if getattr(o, 'partner_shipping_id', False) else ''),
                    (o.partner_shipping_id.name if getattr(o, 'partner_shipping_id', False) else ''),
                    (str(o.user_id.id) if getattr(o, 'user_id', False) else ''),
                    (o.user_id.name if getattr(o, 'user_id', False) else ''),
                    (o.currency_id.name if getattr(o, 'currency_id', False) else ''),
                    (o.payment_term_id.name if getattr(o, 'payment_term_id', False) else ''),
                    getattr(o, 'amount_untaxed', 0.0) or 0.0,
                    getattr(o, 'amount_tax', 0.0) or 0.0,
                    getattr(o, 'amount_total', 0.0) or 0.0,
                    o.invoice_status or '',
                    ', '.join([t.name for t in getattr(o, 'tag_ids', [])]) if getattr(o, 'tag_ids', False) else '',
                    self._m2o_name(getattr(o, 'x_studio_commercial_1', None)) or (getattr(o, 'x_studio_commercial_1', '') or ''),
                    self._m2o_name(getattr(o, 'x_studio_srie', None)) or (getattr(o, 'x_studio_srie', '') or ''),
                    self._m2o_name(getattr(o, 'x_studio_gamme', None)) or (getattr(o, 'x_studio_gamme', '') or ''),
                    getattr(o, 'x_studio_avancement', '') or '',
                    self._m2o_name(getattr(o, 'x_studio_bureau_dtude', None)) or (getattr(o, 'x_studio_bureau_dtude', '') or ''),
                    self._m2o_name(getattr(o, 'x_studio_projet', None)) or (getattr(o, 'x_studio_projet', '') or ''),
                    getattr(o, 'so_delai_confirme_en_semaine', '') or '',
                    getattr(o, 'so_commande_client', '') or '',
                    self._m2o_name(getattr(o, 'x_studio_mode_de_rglement', None)) or (getattr(o, 'x_studio_mode_de_rglement', '') or ''),
                    o.so_date_de_reception_devis.strftime('%Y-%m-%d') if getattr(o, 'so_date_de_reception_devis', False) else '',
                    o.so_date_du_devis.strftime('%Y-%m-%d') if getattr(o, 'so_date_du_devis', False) else '',
                    o.so_date_de_modification_devis.strftime('%Y-%m-%d') if getattr(o, 'so_date_de_modification_devis', False) else '',
                    o.so_date_devis_valide.strftime('%Y-%m-%d') if getattr(o, 'so_date_devis_valide', False) else '',
                    o.so_date_ARC.strftime('%Y-%m-%d') if getattr(o, 'so_date_ARC', False) else '',
                    o.so_date_bpe.strftime('%Y-%m-%d') if getattr(o, 'so_date_bpe', False) else '',
                    o.so_date_bon_pour_fab.strftime('%Y-%m-%d') if getattr(o, 'so_date_bon_pour_fab', False) else '',
                    o.so_date_de_fin_de_production_reel.strftime('%Y-%m-%d') if getattr(o, 'so_date_de_fin_de_production_reel', False) else '',
                    o.so_date_de_livraison.strftime('%Y-%m-%d') if getattr(o, 'so_date_de_livraison', False) else '',
                    o.so_date_de_livraison_prevu.strftime('%Y-%m-%d') if getattr(o, 'so_date_de_livraison_prevu', False) else '',
                ) for o in orders]

                order_headers = [
                    'ID Commande','Num Commande','Etat','Date Creation Devis (ODOO)','Origine',
                    'ID Client','Client','ID Facturation','Adresse Facturation',
                    'ID Livraison','Adresse Livraison',
                    'ID BEC Ventes ','BEC Ventes',
                    'Devise','Conditions de paiement',
                    'Mtt_HT','TVA','Mtt_TTC','Statut_facturation',
                    'Tags',
                    'Commercial','Serie','Gamme','Avancement','BET Méthodes','Projet',
                    'Delai confirmé en semaine','Commande client','Mode de reglement',
                    'Date recep demande devis','Date creation devis','Derniere Date modif devis','Date validation devis par le client',
                    'Date envoi ARC','Date BPE','Date debut de fab','Date fin de fab',
                    'Date de livraison prévue','Date de livraison reelle'
                ]

                order_file = self._write_xml(
                    temp_dir,
                    'commandes.xml',
                    root_tag='commandes',
                    row_tag='commande',
                    headers=order_headers,
                    rows=order_data,
                )
                self._create_attachment(order_file, os.path.basename(order_file))
                _logger.info("[Export Groom] Commandes: %s lignes", len(order_data))
            except Exception as e:
                _logger.exception("[Export Groom] ERREUR section Commandes: %s", e)

            # =========================================================
            # Lignes de commandes (sale.order.line)
            # =========================================================
            try:
                order_lines = self.env['sale.order.line'].search([('product_id', '!=', False)])
                order_line_data = [(
                    str(l.id),
                    getattr(l, 'sequence', 10),
                    (str(l.order_id.id) if getattr(l, 'order_id', False) else ''),
                    (l.order_id.name if getattr(l, 'order_id', False) else ''),
                    (l.order_id.x_studio_projet if getattr(l, 'order_id', False) else ''),
                    getattr(l, 'name', '') or '',
                    (getattr(l, 'display_type', '') or ''),
                    (l.order_id.state if getattr(l, 'order_id', False) else ''),
                    (l.order_id.date_order.strftime('%Y-%m-%d %H:%M:%S') if (getattr(l, 'order_id', False) and getattr(l.order_id, 'date_order', False)) else ''),
                    (str(l.order_id.partner_id.id) if (getattr(l, 'order_id', False) and getattr(l.order_id, 'partner_id', False)) else ''),
                    (l.order_id.partner_id.name if (getattr(l, 'order_id', False) and getattr(l.order_id, 'partner_id', False)) else ''),
                    (str(l.product_id.id) if getattr(l, 'product_id', False) else ''),
                    (l.product_id.default_code if getattr(l, 'product_id', False) else '') or '',
                    (l.product_id.name if getattr(l, 'product_id', False) else '') or '',
                    (l.product_id.categ_id.name if (getattr(l, 'product_id', False) and getattr(l.product_id, 'categ_id', False)) else '') or '',
                    getattr(l, 'product_uom_qty', 0.0) or 0.0,
                    getattr(l, 'qty_delivered', 0.0) or 0.0,
                    getattr(l, 'qty_invoiced', 0.0) or 0.0,
                    (l.product_uom.name if getattr(l, 'product_uom', False) else ''),
                    getattr(l, 'price_unit', 0.0) or 0.0,
                    getattr(l, 'discount', 0.0) or 0.0,
                    ((getattr(l, 'price_unit', 0.0) or 0.0) * (1 - (getattr(l, 'discount', 0.0) or 0.0) / 100.0)),
                    ', '.join([t.name for t in getattr(l, 'tax_id', [])]) if getattr(l, 'tax_id', False) else '',
                    getattr(l, 'price_subtotal', 0.0) or 0.0,
                    getattr(l, 'price_tax', 0.0) or 0.0,
                    getattr(l, 'price_total', 0.0) or 0.0,
                    (l.currency_id.name if getattr(l, 'currency_id', False) else ''),
                ) for l in order_lines]

                order_line_headers = [
                    'ID Ligne','Ordre affichage',
                    'ID Commande','Num Commande','Affaire','Description','Type de ligne','Etat_commande','Date_commande',
                    'ID Client','Client',
                    'ID Article','Code article','Nom article','Categorie_article',
                    'Qte Cde','Qte Liv','Qte Fact','Unité de Mesure',
                    'PU HT','Pourcentage Remise','Prix Unitaire Remise','Taxes','Mtt_Tot_HT','TVA','Mtt_Tot_TTC',
                    'Devise'
                ]

                order_line_file = self._write_xml(
                    temp_dir,
                    'lignes_commandes.xml',
                    root_tag='lignes_commandes',
                    row_tag='ligne_commande',
                    headers=order_line_headers,
                    rows=order_line_data,
                )
                self._create_attachment(order_line_file, os.path.basename(order_line_file))
                _logger.info("[Export Groom] Lignes de commandes: %s lignes", len(order_line_data))
            except Exception as e:
                _logger.exception("[Export Groom] ERREUR section Lignes de commandes: %s", e)

           

        except Exception as e:
            _logger.exception("Erreur globale lors de la génération des fichiers GROOM XML : %s", e)

    # ---------------------------------------------------------
    # CRON : envoi des fichiers XML vers SFTP
    # ---------------------------------------------------------

    @api.model
    def cron_send_files_to_sftp(self):
        """Envoie les fichiers XML générés vers le serveur SFTP."""

        ICP = self.env['ir.config_parameter'].sudo()
        host = ICP.get_param('export_groom.sftp_host', '194.206.49.72')
        port = int(ICP.get_param('export_groom.sftp_port', '22'))
        username = ICP.get_param('export_groom.sftp_username', 'csproginov')
        # ⚠️ À adapter : ne laisse pas un mot de passe en dur en prod
        password = ICP.get_param('export_groom.sftp_password', 'CHANGE_ME')
        remote_path = ICP.get_param('export_groom.sftp_remote_path', 'FMA/OUT/POWERBI/')

        if not all([host, username, remote_path, password]):
            _logger.error("❌ Paramètres SFTP manquants ou incomplets.")
            return

        temp_dir = Path(self._get_or_create_temp_dir())

        if not temp_dir.exists():
            _logger.error("❌ Le dossier temporaire n'existe pas : %s", temp_dir)
            return

        if not os.access(str(temp_dir), os.R_OK):
            _logger.error("❌ Pas de droits de lecture sur : %s", temp_dir)
            return

        # On ne prend que les .xml
        files_to_send = [f for f in temp_dir.iterdir() if f.is_file() and f.suffix in ['.xml']]

        if not files_to_send:
            _logger.info("ℹ️ Aucun fichier XML à envoyer depuis %s.", temp_dir)
            return

        _logger.info("[SFTP] %s fichier(s) XML trouvé(s) à envoyer.", len(files_to_send))

        transport = None
        sftp = None
        try:
            transport = paramiko.Transport((host, port))
            transport.connect(username=username, password=password)
            sftp = paramiko.SFTPClient.from_transport(transport)
            _logger.info("✅ Connexion SFTP réussie à %s:%s", host, port)

            self._mkdir_p_sftp(sftp, remote_path)

            sent = 0
            for file_path in files_to_send:
                try:
                    remote_file = posixpath.join(remote_path.rstrip('/'), file_path.name)
                    sftp.put(str(file_path), remote_file)
                    _logger.info("📤 Fichier envoyé : %s -> %s", file_path.name, remote_file)
                    sent += 1

                    try:
                        file_path.unlink()
                        _logger.info("🗑️ Fichier local supprimé : %s", file_path.name)
                    except Exception as e:
                        _logger.warning("⚠️ Impossible de supprimer %s : %s", file_path.name, e)

                except Exception as e:
                    _logger.exception("❌ Erreur lors de l'envoi de %s : %s", file_path.name, e)

            _logger.info("✅ %s fichier(s) XML envoyé(s) avec succès vers %s", sent, remote_path)

        except paramiko.AuthenticationException:
            _logger.error("❌ Échec d'authentification SFTP. Vérifiez username/password.")
        except paramiko.SSHException as e:
            _logger.exception("❌ Erreur SSH lors de la connexion SFTP : %s", e)
        except Exception as e:
            _logger.exception("❌ Erreur lors de l'envoi des fichiers vers le SFTP : %s", e)
        finally:
            try:
                if sftp:
                    sftp.close()
                if transport:
                    transport.close()
                _logger.info("[SFTP] Connexion fermée.")
            except Exception as e:
                _logger.warning("⚠️ Erreur lors de la fermeture SFTP : %s", e)
