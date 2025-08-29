
# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import csv
import io
import logging
import os
import tempfile
import paramiko  # ADD
from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    outstandings = fields.Float()

    def cron_update_outstandings(self):
        """Compute outstandings for customers from ENCOURS_DAte.csv on SFTP server."""
        # --- Paramètres (idéalement via ir.config_parameter) ---
        # get_param = self.env['ir.config_parameter'].sudo().get_param
        # ftp_server_host = get_param('fma_customer_outstanding.ftp_server_host')
        # ftp_server_username = get_param('fma_customer_outstanding.ftp_server_username')
        # ftp_server_password = get_param('fma_customer_outstanding.ftp_server_password')
        # ftp_server_file_path = get_param('fma_customer_outstanding.ftp_server_file_path')
        ftp_server_host = '194.206.49.72'
        ftp_server_username = 'csproginov'
        ftp_server_password = 'g%tumR/n49:1=5qES6CT'
        ftp_server_file_path = 'FMA/IN/'  # attention: dossier relatif vs absolu
        filename = 'ENCOURS_DAte.csv'

        try:
            if not all([ftp_server_host, ftp_server_username, ftp_server_password, ftp_server_file_path]):
                _logger.error("Missing one or more SFTP credentials or path.")
                return

            _logger.warning("SFTP host=%s user=%s path=%s", ftp_server_host, ftp_server_username, ftp_server_file_path)

            transport = None
            sftp = None
            local_path = None

            try:
                # Connexion SFTP
                transport = paramiko.Transport((ftp_server_host, 22))
                transport.connect(username=ftp_server_username, password=ftp_server_password)
                sftp = paramiko.SFTPClient.from_transport(transport)

                # Se placer dans le dossier cible (ou donner le chemin complet dans get)
                try:
                    sftp.chdir(ftp_server_file_path)
                except IOError:
                    _logger.error("SFTP path not found or not accessible: %s", ftp_server_file_path)
                    return

                # Log des fichiers disponibles AVANT fermeture
                try:
                    _logger.warning("Fichiers dans le dossier : %s", sftp.listdir('.'))
                except Exception as e:
                    _logger.warning("Impossible de lister le dossier SFTP: %s", e)

                # Téléchargement dans un fichier temporaire
                with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                    local_path = tmp_file.name

                sftp.get(filename, local_path)

            except Exception as sftp_error:
                _logger.error("Error while connecting or retrieving file from SFTP: %s", sftp_error)
                return
            finally:
                # Fermer SFTP proprement
                try:
                    if sftp:
                        sftp.close()
                finally:
                    if transport:
                        transport.close()

            # Lecture du contenu et mise à jour
            if not local_path or not os.path.exists(local_path):
                _logger.error("Local temp file not found after SFTP get.")
                return

            try:
                with open(local_path, 'rb') as f:
                    file_content = io.BytesIO(f.read())
                file_content.seek(0)
                self._update_customer_outstandings(file_content)
                _logger.info("Customer outstandings successfully updated from %s.", filename)
            finally:
                try:
                    os.remove(local_path)
                except Exception as _:
                    pass

        except Exception as e:
            _logger.error("Failed to download customer file %s from SFTP server: %s", filename, e)

    def _update_customer_outstandings(self, file_content):
        """Parse CSV file and update customer outstandings.

        CSV attendu avec séparateur ';' et colonnes:
        0: code_client (clé Proginov)
        1: debit
        2: credit
        """
        # Parse CSV (UTF-8; si encodage différent, adapter)
        text = file_content.getvalue().decode('utf-8', errors='ignore')
        csv_reader = csv.reader(io.StringIO(text), delimiter=';')

        rows = []
        for i, row in enumerate(csv_reader):
            # Skip lignes vides
            if not row or len(row) < 3:
                continue
            # Skip header si détecté (par exemple si 'debit' est non numérique)
            if i == 0:
                try:
                    float(row[1].replace(',', '.'))
                    float(row[2].replace(',', '.'))
                except Exception:
                    # c'est probablement l'entête → on saute
                    continue
            rows.append(row)

        if not rows:
            _logger.warning("No valid data rows found in CSV.")
            return

        # Collecte des codes clients Proginov (col 0)
        customer_codes = [r[0] for r in rows]
        # Vérifications de base
        champ = 'x_studio_compte'  # essaie 'ref' si besoin
        if champ not in self._fields:
            _logger.warning("Champ %s inexistant sur res.partner. Champs dispo (extrait): %s",
                            champ, list(self._fields.keys())[:50])
        # Récupération des partenaires par leur code Proginov
        customers = self.search([('x_studio_compte', 'in', customer_codes)])
        customer_map = {c.x_studio_compte: c for c in customers}
        _logger.info("Trouvés en base: %s", [c.x_studio_compte for c in customers])
        # Mise à jour des soldes
        updated = 0
        for row in rows:
            cod = row[0]
            code = (cod[3:])
            _logger.info(" N° Compte %s", code)
            debit = float(row[1].replace(',', '.'))
            credit = float(row[2].replace(',', '.'))
            outstandings = debit + credit

            customer = customer_map.get(code)
            if customer:
                customer.outstandings = outstandings
                # Adapter ces champs si nécessaires/existent
                if hasattr(customer, 'x_studio_mtt_echu'):
                    customer.x_studio_mtt_echu = debit
                if hasattr(customer, 'x_studio_mtt_non_echu'):
                    customer.x_studio_mtt_non_echu = credit
                updated += 1

        _logger.info("Updated outstandings for %s/%s customers.", updated, len(rows))
