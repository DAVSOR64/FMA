import logging
import os

_logger = logging.getLogger(__name__)

class ExportCustomerFile:
    def __init__(self, sftp_path):
        self.sftp_path = sftp_path

    def _get_file_content(self, partners):
        """
        Génère le contenu du fichier pour une liste de partenaires.
        """
        content_lines = []
        for partner in partners:
            try:
                # Vérification des champs avec des valeurs par défaut
                part_code = str(partner.part_code_tiers or '').ljust(9)
                name = 'SA   ' + str(partner.name or '').ljust(30)
                phone = str(partner.phone or '').ljust(20)
                commercial = str(partner.part_commercial or '').ljust(50)
                encours_max = str(partner.encours_max or '').ljust(13)
                zip_code = (
                    str(partner.invoice_ids[0].partner_id.zip or '').ljust(20)
                    if partner.invoice_ids else str(partner.zip or '').ljust(20)
                )
                street = (
                    str(partner.invoice_ids[0].partner_id.street or '').ljust(38)
                    if partner.invoice_ids else str(partner.street or '').ljust(38)
                )
                street2 = (
                    str(partner.invoice_ids[0].partner_id.street2 or 'vide').ljust(38)
                    if partner.invoice_ids else str(partner.street2 or 'vide').ljust(38)
                )
                state = (
                    str(partner.invoice_ids[0].partner_id.state_id.name or '').ljust(38)
                    if partner.invoice_ids else str(partner.state_id.name or '').ljust(38)
                )
                email = str(partner.email or '').ljust(100)
                city = (
                    str(partner.invoice_ids[0].partner_id.city or '').ljust(26)
                    if partner.invoice_ids else str(partner.city or '').ljust(26)
                )

                # Gestion des banques
                bank_name = (
                    partner.bank_ids[0].bank_id.name.ljust(5)
                    if partner.bank_ids and partner.bank_ids[0].bank_id.name else '     '
                )
                bank_acc = (
                    partner.bank_ids[0].acc_number.ljust(23)
                    if partner.bank_ids and partner.bank_ids[0].acc_number else '     '
                )

                # Construction de la ligne
                line = [
                    'PCC', 'I', part_code, name, '0', 'N', 'N', 'N', 'N', '0     ', 'O', 'D', 'N',
                    'N', 'O', 'N', ' ', '         ', '0   ', '  ', 'N', 'N', '0  ', '   ', 'A41',
                    '   ', '        ', '    ', name.ljust(25), '                              ',
                    '                              ', '0    ', '                        ',
                    'FRA', phone, '                    ', '                    ', '    ',
                    str(partner.x_studio_char_field_G6qIE or '').ljust(14), '      ',
                    '              ', '                         ', commercial, encours_max,
                    'EUR', '  ', '  ', '                        ', '                        ',
                    bank_name, bank_acc, 'O', 'O', 'O', '   ', '          ', 'O', '0000', '   ',
                    '   ', '               ', 'O', '            ', 'O', '            ', '0',
                    '     ', 'N', 'O', '1 ', zip_code, '                              ',
                    '@                             ', '@                       ',
                    '@                       ', '@    ', '@    ', '@          ', '@ ',
                    '@                             ', '@                       ',
                    '@                       ', '@    ', '@    ', '@          ', '@ ',
                    '1', '                                  ', '                    ',
                    '                                 ', '                    ',
                    '                                  ', '                     ',
                    '        ', '                    ', 'N', '                                                            ',
                    '      ', '@        ', street, street2, state, email, '                            ',
                    city, '00001', 'papier    ', '                                                            '
                ]

                # Ajout de la ligne au contenu
                content_lines.append(''.join(line))

            except Exception as e:
                # Gestion des erreurs et log
                _logger.error(f"Erreur lors de la construction de la ligne pour le partenaire {partner.id}: {e}")
                continue  # Passer au partenaire suivant en cas d'erreur

        return "\n".join(content_lines)

    def _sync_file(self, filename, content):
        """
        Synchronise un fichier vers un emplacement SFTP.
        """
        try:
            # Vérifie que le chemin existe
            os.makedirs(self.sftp_path, exist_ok=True)

            # Chemin complet du fichier
            file_path = os.path.join(self.sftp_path, filename)

            # Écriture du contenu dans le fichier
            with open(file_path, 'w') as file:
                file.write(content)

            _logger.info(f"Fichier écrit avec succès : {file_path}")
        except Exception as e:
            _logger.error(f"Erreur lors de la synchronisation du fichier : {e}")
            raise

    def export_customers(self, partners):
        """
        Exporte les données des partenaires dans un fichier sur le SFTP.
        """
        try:
            # Génération du contenu
            content = self._get_file_content(partners)

            # Nom du fichier avec date
            filename = f"export_clients_{time.strftime('%Y%m%d_%H%M%S')}.txt"

            # Synchronisation du fichier
            self._sync_file(filename, content)
        except Exception as e:
            _logger.error(f"Erreur lors de l'export des clients : {e}")
            raise
