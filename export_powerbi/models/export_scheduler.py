import tempfile
import os
import shutil
import base64
import paramiko
import xlsxwriter
from datetime import datetime, date
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

        # helper pour formater un float d'heure (ex: 8.5) en '08:30'
        def _float_to_hhmm(val):
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

        # helper M2O -> texte (safe)
        def _m2o_name(val):
            try:
                if not val:
                    return ''
                name = getattr(val, 'name', None)
                if name is None:
                    # pas un record -> renvoyer valeur brute
                    return val
                return name or ''
            except Exception:
                return ''

        # Sanitize universel: convertit toute valeur en type "écrivible" par xlsxwriter
        def _to_cell(v):
            try:
                if v is None:
                    return ''
                # primitifs
                if isinstance(v, (int, float, bool)):
                    return v
                if isinstance(v, str):
                    return v
                if isinstance(v, (datetime,)):
                    return v.strftime('%Y-%m-%d %H:%M:%S')
                if isinstance(v, (date,)):
                    return v.strftime('%Y-%m-%d')
                if isinstance(v, (bytes, bytearray)):
                    try:
                        return v.decode('utf-8', errors='ignore')
                    except Exception:
                        return str(v)
                # recordset Odoo
                try:
                    from odoo.models import BaseModel
                    if isinstance(v, BaseModel):
                        if not v:
                            return ''
                        if len(v) == 1:
                            return getattr(v, 'display_name', None) or getattr(v, 'name', None) or v.id
                        parts = []
                        for rec in v:
                            parts.append(getattr(rec, 'display_name', None) or getattr(rec, 'name', None) or str(rec.id))
                        return ', '.join([str(p) for p in parts])
                except Exception:
                    pass
                # itérables standards
                if isinstance(v, (list, tuple, set)):
                    parts = [_to_cell(x) for x in v]
                    return ', '.join([str(p) for p in parts])
                # fallback
                return str(v)
            except Exception:
                return str(v)

        def write_xlsx(filename, headers, rows):
            filepath = os.path.join(temp_dir, filename)
            workbook = xlsxwriter.Workbook(filepath)
            worksheet = workbook.add_worksheet()
            # en-têtes
            for col, header in enumerate(headers):
                worksheet.write(0, col, header)
            # lignes
            for row_idx, row in enumerate(rows, 1):
                for col_idx, cell in enumerate(row):
                    worksheet.write(row_idx, col_idx, _to_cell(cell))
            workbook.close()
            return filepath

        def create_attachment(filepath, name):
            with open(filepath, 'rb') as f:
                file_content = f.read()
            self.env['ir.attachment'].create({
                'name': name,
                'type': 'binary',
                'datas': base64.b64encode(file_content).decode(),  # s'assurer que c'est une str
                'res_model': 'export.sftp.scheduler',
                'res_id': 0,  # Pas de record spécifique
                'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            })
            _logger.info(f"[Export Power BI] Pièce jointe créée : {name}")

        try:
            # ==================== Clients ====================
            try:
                clients = self.env['res.partner'].search([('customer_rank', '>', 0), ('is_company', '=', True)])
                client_data = [(
                    # Identité / hiérarchie
                    p.id,
                    p.name or '',
                    getattr(p, 'display_name', '') or '',
                    getattr(p, 'ref', '') or '',
                    getattr(p, 'company_type', '') or '',
                    bool(getattr(p, 'is_company', False)),
                    (p.parent_id.id if getattr(p, 'parent_id', False) else ''),
                    (p.parent_id.name if getattr(p, 'parent_id', False) else ''),
                    getattr(p, 'commercial_company_name', '') or '',
                    (p.commercial_partner_id.id if getattr(p, 'commercial_partner_id', False) else ''),
                    (p.commercial_partner_id.name if getattr(p, 'commercial_partner_id', False) else ''),
                    # Coordonnées
                    p.street or '',
                    getattr(p, 'street2', '') or '',
                    p.city or '',
                    (p.state_id.code if getattr(p, 'state_id', False) else ''),
                    (p.state_id.name if getattr(p, 'state_id', False) else ''),
                    p.zip or '',
                    (p.country_id.code if getattr(p, 'country_id', False) else ''),
                    (p.country_id.name if getattr(p, 'country_id', False) else ''),
                    p.phone or '',
                    getattr(p, 'mobile', '') or '',
                    p.email or '',
                    getattr(p, 'website', '') or '',
                    # Fiscal / ventes
                    p.vat or '',
                    getattr(p, 'barcode', '') or '',
                    getattr(p, 'industry_id', False) and (p.industry_id.name or '') or '',
                    getattr(p, 'customer_rank', 0) or 0,
                    getattr(p, 'supplier_rank', 0) or 0,
                    getattr(p, 'credit_limit', 0.0) or 0.0,
                    getattr(p, 'property_payment_term_id', False) and (p.property_payment_term_id.name or '') or '',
                    getattr(p, 'property_product_pricelist', False) and (p.property_product_pricelist.name or '') or '',
                    getattr(p, 'property_account_position_id', False) and (p.property_account_position_id.name or '') or '',
                    # Commercial / société / utilisateur
                    (p.user_id.id if getattr(p, 'user_id', False) else ''),
                    (p.user_id.name if getattr(p, 'user_id', False) else ''),
                    (p.company_id.id if getattr(p, 'company_id', False) else ''),
                    (p.company_id.name if getattr(p, 'company_id', False) else ''),
                    # Préférences
                    getattr(p, 'lang', '') or '',
                    getattr(p, 'tz', '') or '',
                    # Tags, banques, enfants
                    ', '.join([c.name for c in getattr(p, 'category_id', [])]) if getattr(p, 'category_id', False) else '',
                    ', '.join([b.acc_number for b in getattr(p, 'bank_ids', [])]) if getattr(p, 'bank_ids', False) else '',
                    len(getattr(p, 'child_ids', [])) if getattr(p, 'child_ids', False) else 0,
                    # Champs personnalisés demandés
                    getattr(p, 'x_studio_ref_logikal', '') or '',
                    _m2o_name(getattr(p, 'x_studio_commercial_1', None)) or (getattr(p, 'x_studio_commercial_1', '') or ''),
                    getattr(p, 'x_studio_gneration_n_compte_1', '') or '',
                    getattr(p, 'x_studio_compte', '') or '',
                    getattr(p, 'x_studio_code_diap', '') or '',
                    # Statut / notes / dates
                    bool(getattr(p, 'active', True)),
                    getattr(p, 'comment', '') or '',
                    p.create_date.strftime('%Y-%m-%d %H:%M:%S') if getattr(p, 'create_date', False) else '',
                    p.write_date.strftime('%Y-%m-%d %H:%M:%S') if getattr(p, 'write_date', False) else '',
                ) for p in clients]
                client_file = write_xlsx(
                    f'clients_{today}.xlsx',
                    [
                        'ID','Nom','Nom affiché','Référence','Type société','Est société',
                        'ID Parent','Parent','Société commerciale','ID Partenaire commercial','Partenaire commercial',
                        'Rue','Rue 2','Ville','Code État','État','Code Postal','Code Pays','Pays',
                        'Téléphone','Mobile','Email','Site web',
                        'TVA','Code-barres','Secteur','Rang client','Rang fournisseur','Limite de crédit',
                        'Terme de paiement','Liste de prix','Position fiscale',
                        'ID Commercial','Commercial','ID Société','Société',
                        'Langue','Fuseau horaire',
                        'Tags','IBAN/Comptes bancaires','Nb. enfants',
                        'x_studio_ref_logikal','x_studio_commercial_1','x_studio_gneration_n_compte_1','x_studio_compte','x_studio_code_diap',
                        'Actif','Note','Créé le','Modifié le'
                    ],
                    client_data
                )
                create_attachment(client_file, os.path.basename(client_file))
                _logger.info("[Export Power BI] Clients: %s lignes", len(client_data))
            except Exception as e:
                _logger.exception("[Export Power BI] ERREUR section Clients: %s", e)

            # ==================== Commandes ====================
            try:
                orders = self.env['sale.order'].search([])
                order_data = [(
                    o.id,
                    o.name or '',
                    o.state or '',
                    o.date_order.strftime('%Y-%m-%d %H:%M:%S') if getattr(o, 'date_order', False) else '',
                    getattr(o, 'validity_date', False) and o.validity_date.strftime('%Y-%m-%d') or '',
                    o.origin or '',
                    getattr(o, 'client_order_ref', '') or '',
                    # Partenaires
                    (o.partner_id.id if getattr(o, 'partner_id', False) else ''),
                    (o.partner_id.name if getattr(o, 'partner_id', False) else ''),
                    (o.partner_invoice_id.id if getattr(o, 'partner_invoice_id', False) else ''),
                    (o.partner_invoice_id.name if getattr(o, 'partner_invoice_id', False) else ''),
                    (o.partner_shipping_id.id if getattr(o, 'partner_shipping_id', False) else ''),
                    (o.partner_shipping_id.name if getattr(o, 'partner_shipping_id', False) else ''),
                    # Commercial / orga
                    (o.user_id.id if getattr(o, 'user_id', False) else ''),
                    (o.user_id.name if getattr(o, 'user_id', False) else ''),
                    (o.team_id.id if getattr(o, 'team_id', False) else ''),
                    (o.team_id.name if getattr(o, 'team_id', False) else ''),
                    (o.company_id.id if getattr(o, 'company_id', False) else ''),
                    (o.company_id.name if getattr(o, 'company_id', False) else ''),
                    # Logistique / incoterm
                    getattr(o, 'picking_policy', '') or '',
                    getattr(o, 'commitment_date', False) and o.commitment_date.strftime('%Y-%m-%d %H:%M:%S') or '',
                    (o.warehouse_id.id if getattr(o, 'warehouse_id', False) else ''),
                    (o.warehouse_id.name if getattr(o, 'warehouse_id', False) else ''),
                    (o.incoterm.id if getattr(o, 'incoterm', False) else ''),
                    (o.incoterm.name if getattr(o, 'incoterm', False) else ''),
                    # Prix / devises / conditions
                    (o.currency_id.name if getattr(o, 'currency_id', False) else ''),
                    (o.pricelist_id.name if getattr(o, 'pricelist_id', False) else ''),
                    (o.payment_term_id.name if getattr(o, 'payment_term_id', False) else ''),
                    (o.fiscal_position_id.name if getattr(o, 'fiscal_position_id', False) else ''),
                    # Montants
                    getattr(o, 'amount_untaxed', 0.0) or 0.0,
                    getattr(o, 'amount_tax', 0.0) or 0.0,
                    getattr(o, 'amount_total', 0.0) or 0.0,
                    o.invoice_status or '',
                    # Méta
                    ', '.join([t.name for t in getattr(o, 'tag_ids', [])]) if getattr(o, 'tag_ids', False) else '',
                    getattr(o, 'note', '') or '',
                    getattr(o, 'confirmation_date', False) and o.confirmation_date.strftime('%Y-%m-%d %H:%M:%S') or '',
                    o.create_date.strftime('%Y-%m-%d %H:%M:%S') if getattr(o, 'create_date', False) else '',
                    o.write_date.strftime('%Y-%m-%d %H:%M:%S') if getattr(o, 'write_date', False) else '',
                    # -------- Champs personnalisés "devis" (sale.order) --------
                    _m2o_name(getattr(o, 'x_studio_commercial_1', None)) or (getattr(o, 'x_studio_commercial_1', '') or ''),
                    _m2o_name(getattr(o, 'x_studio_srie', None)) or (getattr(o, 'x_studio_srie', '') or ''),
                    _m2o_name(getattr(o, 'x_studio_gamme', None)) or (getattr(o, 'x_studio_gamme', '') or ''),
                    getattr(o, 'x_studio_avancement', '') or '',
                    _m2o_name(getattr(o, 'x_studio_bureau_dtude', None)) or (getattr(o, 'x_studio_bureau_dtude', '') or ''),
                    _m2o_name(getattr(o, 'x_studio_projet', None)) or (getattr(o, 'x_studio_projet', '') or ''),
                    getattr(o, 'so_delai_confirme_en_semaine', '') or '',
                    getattr(o, 'so_commande_client', '') or '',
                    getattr(o, 'so_acces_bl', '') or '',
                    getattr(o, 'so_type_camion_bl', '') or '',  # Selection -> string
                    _float_to_hhmm(getattr(o, 'so_horaire_ouverture_bl', '')),
                    _float_to_hhmm(getattr(o, 'so_horaire_fermeture_bl', '')),
                    _m2o_name(getattr(o, 'x_studio_mode_de_rglement', None)) or (getattr(o, 'x_studio_mode_de_rglement', '') or ''),
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
                order_file = write_xlsx(
                    f'commandes_{today}.xlsx',
                    [
                        'ID','Référence','État','Date commande','Date validité','Origine','Réf client',
                        'ID Client','Client','ID Facturation','Adresse Facturation',
                        'ID Livraison','Adresse Livraison',
                        'ID Commercial','Commercial','ID Équipe','Équipe',
                        'ID Société','Société',
                        'Politique picking','Date engagement','ID Entrepôt','Entrepôt',
                        'ID Incoterm','Incoterm',
                        'Devise','Liste de prix','Terme de paiement','Position fiscale',
                        'Montant HT','TVA','Montant TTC','Statut facturation',
                        'Tags','Note','Confirmée le','Créé le','Modifié le',
                        'Commercial (x_studio)','Série','Gamme','Avancement','Bureau d\'étude','Projet',
                        'Délai confirmé (semaines)','Commande client','Accès BL','Type camion BL',
                        'Horaire ouverture BL','Horaire fermeture BL','Mode de règlement (x_studio)',
                        'Date réception devis','Date du devis','Date modification devis','Date devis validé',
                        'Date ARC','Date BPE','Date bon pour fab','Date fin de production (réel)',
                        'Date de livraison','Date de livraison prévue'
                    ],
                    order_data
                )
                create_attachment(order_file, os.path.basename(order_file))
                _logger.info("[Export Power BI] Commandes: %s lignes", len(order_data))
            except Exception as e:
                _logger.exception("[Export Power BI] ERREUR section Commandes: %s", e)

            # ==================== Lignes de commandes ====================
            try:
                order_lines = self.env['sale.order.line'].search([('product_id', '!=', False)])
                order_line_data = [(
                    l.id,
                    getattr(l, 'sequence', 10),
                    # Lien commande
                    (l.order_id.id if getattr(l, 'order_id', False) else ''),
                    (l.order_id.name if getattr(l, 'order_id', False) else ''),
                    getattr(l, 'name', '') or '',
                    (getattr(l, 'display_type', '') or ''),
                    (l.order_id.state if getattr(l, 'order_id', False) else ''),
                    (l.order_id.date_order.strftime('%Y-%m-%d %H:%M:%S') if (getattr(l, 'order_id', False) and getattr(l.order_id, 'date_order', False)) else ''),
                    # Client
                    (l.order_id.partner_id.id if (getattr(l, 'order_id', False) and getattr(l.order_id, 'partner_id', False)) else ''),
                    (l.order_id.partner_id.name if (getattr(l, 'order_id', False) and getattr(l.order_id, 'partner_id', False)) else ''),
                    # Produit
                    (l.product_id.id if getattr(l, 'product_id', False) else ''),
                    (l.product_id.default_code if getattr(l, 'product_id', False) else '') or '',
                    (l.product_id.name if getattr(l, 'product_id', False) else '') or '',
                    (l.product_id.categ_id.name if (getattr(l, 'product_id', False) and getattr(l.product_id, 'categ_id', False)) else '') or '',
                    # Quantités / UoM / lead time
                    getattr(l, 'product_uom_qty', 0.0) or 0.0,
                    getattr(l, 'qty_delivered', 0.0) or 0.0,
                    getattr(l, 'qty_invoiced', 0.0) or 0.0,
                    (l.product_uom.name if getattr(l, 'product_uom', False) else ''),
                    getattr(l, 'customer_lead', 0.0) or 0.0,
                    # Prix / taxes / totaux
                    getattr(l, 'price_unit', 0.0) or 0.0,
                    getattr(l, 'discount', 0.0) or 0.0,
                    ', '.join([t.name for t in getattr(l, 'tax_id', [])]) if getattr(l, 'tax_id', False) else '',
                    getattr(l, 'price_subtotal', 0.0) or 0.0,
                    getattr(l, 'price_tax', 0.0) or 0.0,
                    getattr(l, 'price_total', 0.0) or 0.0,
                    # Devise / société / vendeur
                    (l.currency_id.name if getattr(l, 'currency_id', False) else ''),
                    (l.company_id.name if getattr(l, 'company_id', False) else ''),
                    (l.order_id.user_id.name if (getattr(l, 'order_id', False) and getattr(l.order_id, 'user_id', False)) else ''),
                    # Analytique
                    (l.analytic_account_id.name if getattr(l, 'analytic_account_id', False) else ''),
                    ', '.join([t.name for t in getattr(l, 'analytic_tag_ids', [])]) if getattr(l, 'analytic_tag_ids', False) else '',
                    # Dates / meta
                    l.create_date.strftime('%Y-%m-%d %H:%M:%S') if getattr(l, 'create_date', False) else '',
                    l.write_date.strftime('%Y-%m-%d %H:%M:%S') if getattr(l, 'write_date', False) else '',
                ) for l in order_lines]
                order_line_file = write_xlsx(
                    f'lignes_commandes_{today}.xlsx',
                    [
                        'ID Ligne','Sequence',
                        'ID Commande','N° Commande','Description','Type affichage','État commande','Date commande',
                        'ID Client','Client',
                        'ID Article','Code article','Nom article','Catégorie article',
                        'Qté commandée','Qté livrée','Qté facturée','UoM','Délai client (j)',
                        'PU HT','Remise %','Taxes','Sous-total HT','TVA','Total TTC',
                        'Devise','Société','Commercial',
                        'Compte Analytique','Tags analytiques',
                        'Créé le','Modifié le'
                    ],
                    order_line_data
                )
                create_attachment(order_line_file, os.path.basename(order_line_file))
                _logger.info("[Export Power BI] Lignes de commandes: %s lignes", len(order_line_data))
            except Exception as e:
                _logger.exception("[Export Power BI] ERREUR section Lignes de commandes: %s", e)

            # ==================== Factures (ENRICHI) ====================
            try:
                invoices = self.env['account.move'].search([('move_type', '=', 'out_invoice'), ('state', '=', 'posted')])

                invoice_data = []
                for i in invoices:
                    try:
                        row = (
                            # --- Identifiants & état ---
                            i.id,
                            i.name or '',
                            getattr(i, 'state', '') or '',
                            getattr(i, 'move_type', '') or '',
                            # --- Dates ---
                            i.invoice_date.strftime('%Y-%m-%d') if getattr(i, 'invoice_date', False) else '',
                            i.invoice_date_due.strftime('%Y-%m-%d') if getattr(i, 'invoice_date_due', False) else '',
                            i.date.strftime('%Y-%m-%d') if getattr(i, 'date', False) else '',
                            # --- Références ---
                            getattr(i, 'invoice_origin', '') or '',
                            i.ref or '',
                            i.payment_state or '',
                            getattr(i, 'payment_reference', '') or '',
                            # --- Partenaire & coordonnées ---
                            (i.partner_id.id if getattr(i, 'partner_id', False) else ''),
                            (i.partner_id.name if getattr(i, 'partner_id', False) else ''),
                            (i.commercial_partner_id.id if getattr(i, 'commercial_partner_id', False) else ''),
                            (i.commercial_partner_id.name if getattr(i, 'commercial_partner_id', False) else ''),
                            getattr(i.partner_id, 'vat', '') or '',
                            getattr(i.partner_id, 'email', '') or '',
                            getattr(i.partner_id, 'phone', '') or '',
                            getattr(i.partner_id, 'mobile', '') or '',
                            getattr(i.partner_id, 'street', '') or '',
                            getattr(i.partner_id, 'street2', '') or '',
                            getattr(i.partner_id, 'city', '') or '',
                            (getattr(i.partner_id, 'zip', '') or ''),
                            (getattr(getattr(i.partner_id, 'state_id', None), 'name', '') or ''),
                            (getattr(getattr(i.partner_id, 'country_id', None), 'name', '') or ''),
                            # --- Vendeur / société / journal / devise ---
                            (i.invoice_user_id.id if getattr(i, 'invoice_user_id', False) else ''),
                            (i.invoice_user_id.name if getattr(i, 'invoice_user_id', False) else ''),
                            (i.company_id.id if getattr(i, 'company_id', False) else ''),
                            (i.company_id.name if getattr(i, 'company_id', False) else ''),
                            (i.journal_id.id if getattr(i, 'journal_id', False) else ''),
                            (i.journal_id.name if getattr(i, 'journal_id', False) else ''),
                            (i.currency_id.name if getattr(i, 'currency_id', False) else ''),
                            (i.company_currency_id.name if getattr(i, 'company_currency_id', False) else ''),
                            # --- Conditions / fiscales ---
                            (i.invoice_payment_term_id.name if getattr(i, 'invoice_payment_term_id', False) else ''),
                            (i.fiscal_position_id.name if getattr(i, 'fiscal_position_id', False) else ''),
                            (i.invoice_incoterm_id.name if getattr(i, 'invoice_incoterm_id', False) else ''),
                            # --- Banque (émetteur) ---
                            (i.partner_bank_id.acc_number if getattr(i, 'partner_bank_id', False) else ''),
                            (i.partner_bank_id.bank_id.name if getattr(i, 'partner_bank_id', False) else ''),
                            # --- Montants ---
                            getattr(i, 'amount_untaxed', 0.0) or 0.0,
                            getattr(i, 'amount_tax', 0.0) or 0.0,
                            getattr(i, 'amount_total', 0.0) or 0.0,
                            getattr(i, 'amount_residual', 0.0) or 0.0,
                            getattr(i, 'amount_untaxed_signed', 0.0) or 0.0,
                            getattr(i, 'amount_total_signed', 0.0) or 0.0,
                            getattr(i, 'amount_residual_signed', 0.0) or 0.0,
                            # --- Arrondi / autopost / réversion ---
                            (i.invoice_cash_rounding_id.name if getattr(i, 'invoice_cash_rounding_id', False) else ''),
                            getattr(i, 'auto_post', '') or '',
                            i.auto_post_until.strftime('%Y-%m-%d') if getattr(i, 'auto_post_until', False) else '',
                            (getattr(i, 'reversed_entry_id', False) and (i.reversed_entry_id.name or i.reversed_entry_id.id) or ''),
                            (getattr(i, 'reversal_move_id', False) and (i.reversal_move_id.name or i.reversal_move_id.id) or ''),
                            # --- Divers ---
                            getattr(i, 'narration', '') or '',
                            len(getattr(i, 'invoice_line_ids', [])),
                            i.create_date.strftime('%Y-%m-%d %H:%M:%S') if getattr(i, 'create_date', False) else '',
                            i.write_date.strftime('%Y-%m-%d %H:%M:%S') if getattr(i, 'write_date', False) else '',
                            # --- CHAMPS CUSTOM demandés ---
                            getattr(i, 'x_studio_rfrence_affaire', '') or '',
                            _m2o_name(getattr(i, 'x_studio_projet_vente', None)) or (getattr(i, 'x_studio_projet_vente', '') or ''),
                            _m2o_name(getattr(i, 'x_studio_commercial_1_mtn', None)) or (getattr(i, 'x_studio_commercial_1_mtn', '') or ''),
                            _m2o_name(getattr(i, 'x_studio_mode_de_reglement_1', None)) or (getattr(i, 'x_studio_mode_de_reglement_1', '') or ''),
                            getattr(i, 'x_studio_libelle_1', '') or '',
                        )
                        invoice_data.append(row)
                    except Exception as e_row:
                        _logger.exception("[Export Power BI] Facture ID %s ignorée (donnée invalide): %s", getattr(i, 'id', 'n/a'), e_row)

                invoice_file = write_xlsx(
                    f'factures_{today}.xlsx',
                    [
                        # --- Identifiants & état ---
                        'ID','N° Facture','État','Type',
                        # --- Dates ---
                        'Date facture','Date échéance','Date comptable',
                        # --- Références ---
                        'Origine','Référence (ref)','État paiement','Référence paiement',
                        # --- Partenaire & coordonnées ---
                        'ID Client','Client','ID Partenaire commercial','Partenaire commercial',
                        'TVA client','Email client','Téléphone client','Mobile client',
                        'Rue','Rue 2','Ville','Code Postal','État/Province','Pays',
                        # --- Vendeur / société / journal / devise ---
                        'ID Vendeur','Vendeur','ID Société','Société',
                        'ID Journal','Journal','Devise','Devise société',
                        # --- Conditions / fiscales ---
                        'Terme de paiement','Position fiscale','Incoterm',
                        # --- Banque (émetteur) ---
                        'IBAN/Compte bancaire','Banque',
                        # --- Montants ---
                        'Montant HT','TVA','Montant TTC','Solde',
                        'Montant HT signé','Montant TTC signé','Solde signé',
                        # --- Arrondi / autopost / réversion ---
                        'Rounding','Auto-post','Auto-post jusqu\'au',
                        'Écriture d\'origine (si réversion)','Écriture de réversion',
                        # --- Divers ---
                        'Narration','Nb. lignes',
                        'Créé le','Modifié le',
                        # --- CHAMPS CUSTOM ---
                        'x_studio_rfrence_affaire','x_studio_projet_vente',
                        'x_studio_commercial_1_mtn','x_studio_mode_de_reglement_1','x_studio_libelle_1'
                    ],
                    invoice_data
                )
                create_attachment(invoice_file, os.path.basename(invoice_file))
                _logger.info("[Export Power BI] Factures: %s lignes (dont %s ignorées si erreurs)", len(invoice_data), len(invoices) - len(invoice_data))
            except Exception as e:
                _logger.exception("[Export Power BI] ERREUR section Factures: %s", e)

            # ==================== Lignes de factures ====================
            try:
                invoice_lines = self.env['account.move.line'].search([
                    ('move_id.move_type', '=', 'out_invoice'),
                    ('move_id.state', '=', 'posted'),
                    ('product_id', '!=', False)
                ])
                invoice_line_data = [(
                    l.id,
                    getattr(l, 'sequence', 10),
                    # Move / facture
                    (l.move_id.id if getattr(l, 'move_id', False) else ''),
                    (l.move_id.name if getattr(l, 'move_id', False) else ''),
                    (l.move_id.state if getattr(l, 'move_id', False) else ''),
                    (l.move_id.invoice_date.strftime('%Y-%m-%d') if (getattr(l, 'move_id', False) and getattr(l.move_id, 'invoice_date', False)) else ''),
                    (l.move_id.partner_id.id if (getattr(l, 'move_id', False) and getattr(l.move_id, 'partner_id', False)) else ''),
                    (l.move_id.partner_id.name if (getattr(l, 'move_id', False) and getattr(l.move_id, 'partner_id', False)) else ''),
                    (l.move_id.journal_id.name if (getattr(l, 'move_id', False) and getattr(l.move_id, 'journal_id', False)) else ''),
                    # Ligne
                    getattr(l, 'name', '') or '',
                    (getattr(l, 'display_type', '') or ''),
                    # Produit
                    (l.product_id.id if getattr(l, 'product_id', False) else ''),
                    (l.product_id.default_code if getattr(l, 'product_id', False) else '') or '',
                    (l.product_id.name if getattr(l, 'product_id', False) else '') or '',
                    (l.product_id.categ_id.name if (getattr(l, 'product_id', False) and getattr(l.product_id, 'categ_id', False)) else '') or '',
                    # Quantité / UoM
                    getattr(l, 'quantity', 0.0) or 0.0,
                    (getattr(l, 'product_uom_id', False) and l.product_uom_id.name or ''),
                    # Prix / taxes / totaux
                    getattr(l, 'price_unit', 0.0) or 0.0,
                    ', '.join([t.name for t in getattr(l, 'tax_ids', [])]) if getattr(l, 'tax_ids', False) else '',
                    getattr(l, 'price_subtotal', 0.0) or 0.0,
                    getattr(l, 'price_total', 0.0) or 0.0,
                    (l.currency_id.name if getattr(l, 'currency_id', False) else ''),
                    # Comptabilité
                    (l.account_id.code if getattr(l, 'account_id', False) else ''),
                    (l.account_id.name if getattr(l, 'account_id', False) else ''),
                    getattr(l, 'debit', 0.0) or 0.0,
                    getattr(l, 'credit', 0.0) or 0.0,
                    getattr(l, 'balance', 0.0) or 0.0,
                    getattr(l, 'amount_currency', 0.0) or 0.0,
                    # Analytique
                    (l.analytic_account_id.name if getattr(l, 'analytic_account_id', False) else ''),
                    ', '.join([t.name for t in getattr(l, 'analytic_tag_ids', [])]) if getattr(l, 'analytic_tag_ids', False) else '',
                    # Lien vente
                    (l.sale_line_ids[0].id if getattr(l, 'sale_line_ids', False) and l.sale_line_ids else ''),
                    # Champs custom demandés (ligne de facture)
                    getattr(l, 'x_studio_hauteur', '') or '',
                    getattr(l, 'x_studio_largeur', '') or '',
                    getattr(l, 'x_studio_position', '') or '',
                    # Méta
                    l.create_date.strftime('%Y-%m-%d %H:%M:%S') if getattr(l, 'create_date', False) else '',
                    l.write_date.strftime('%Y-%m-%d %H:%M:%S') if getattr(l, 'write_date', False) else '',
                ) for l in invoice_lines]
                invoice_line_file = write_xlsx(
                    f'lignes_factures_{today}.xlsx',
                    [
                        'ID Ligne','Sequence',
                        'ID Facture','N° Facture','État facture','Date facture',
                        'ID Client','Client','Journal',
                        'Libellé','Type affichage',
                        'ID Article','Code article','Nom article','Catégorie article',
                        'Qté','UoM',
                        'PU HT','Taxes','Sous-total HT','Total TTC','Devise',
                        'Compte code','Compte libellé','Débit','Crédit','Balance','Montant devise',
                        'Compte Analytique','Tags analytiques',
                        'ID Ligne Commande',
                        'Hauteur (x_studio)','Largeur (x_studio)','Position (x_studio)',
                        'Créé le','Modifié le'
                    ],
                    invoice_line_data
                )
                create_attachment(invoice_line_file, os.path.basename(invoice_line_file))
                _logger.info("[Export Power BI] Lignes de factures: %s lignes", len(invoice_line_data))
            except Exception as e:
                _logger.exception("[Export Power BI] ERREUR section Lignes de factures: %s", e)

        except Exception as e:
            _logger.exception("Erreur globale lors de la génération des fichiers Power BI : %s", e)

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
