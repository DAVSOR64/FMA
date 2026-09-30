# -*- coding: utf-8 -*-

import base64
import io
import logging
import paramiko
from odoo import _, fields, models
from odoo.exceptions import UserError
from markupsafe import Markup

_logger = logging.getLogger(__name__)

# Point de depart par defaut de la reprise, surchargeable par le parametre
# systeme « fma_customer_export.reprise_depuis ».
DEFAUT_REPRISE_DEPUIS = "2026-08-01"


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_included_in_customers_export_file = fields.Boolean()

    # ⚠️ TEMPORAIRE : commenter si problème persiste
    # attachment_ids = fields.Many2many(
    #     "ir.attachment", "partner_attachment_rel", string="Attachments"
    # )

    encours_max = fields.Char()

    def write(self, vals):
        # ✅ FIX : ne toucher au champ QUE s’il est dans vals
        if "is_included_in_customers_export_file" in vals:
            if not vals.get("is_included_in_customers_export_file"):
                vals["is_included_in_customers_export_file"] = False

        return super().write(vals)

    def _get_file_content(self, partners):
        content_lines = []
        for partner in partners:
            line = [
                "PCC",
                "I",
                str(partner.property_account_receivable_id.code or "").ljust(9),
                str(partner.name or "").ljust(35),
                "0NNNN0",
                "     ",
                "ODNNON",
                "          ",
                "0",
                "     ",
                "NN0",
                "     ",
                "A41",
                "           ",
                (
                    str(partner.x_studio_civilit_1 or "").ljust(4)
                    + str(partner.name or "").ljust(89)
                ),
                "0",
                "                             ",
                "FRA",
                str(partner.phone or "").ljust(64),
                # SIRET : res.partner.siret n'existe plus en v19. Le numero vit
                # dans company_registry, porte par la societe — donc par le
                # partenaire commercial, pas par le contact. Meme lecture que
                # le gabarit de facture, deja en production.
                str(partner.commercial_partner_id.company_registry or "").ljust(14),
                "      ",
                str(partner.vat or "").ljust(14),
                "                                                  ",
                "             ",
                "                         ",
                "EUR",
                str(partner.x_studio_mode_de_rglement_dsa.x_name or "").ljust(2),
                str(partner.x_studio_code or "").ljust(2),
                str(partner.bank_ids[0].bank_id.name or "").ljust(24)
                if partner.bank_ids and partner.bank_ids[0].bank_id
                else "                        ",
                "                        ",
                str(partner.bank_ids[0].acc_number or "").ljust(23)
                if partner.bank_ids and partner.bank_ids[0].acc_number
                else "                       ",
                "OOO",
                "             ",
                "O0000",
                "                     ",
                "0",
                "            ",
                "0",
                "            ",
                "0",
                "     ",
                "NO1",
                "                               ",
                str(
                    partner.invoice_ids[0].partner_id.zip
                    if partner.invoice_ids
                    else partner.zip or ""
                ).ljust(20),
                "                              ",
                "@                             ",
                "@                       ",
                "@                       ",
                "@    ",
                "@    ",
                "@          ",
                "@ ",
                "@                             ",
                "@                       ",
                "@                       ",
                "@    ",
                "@    ",
                "@          ",
                "@ ",
                "1",
                "                                  ",
                "                    ",
                "                                  ",
                "                    ",
                "                                  ",
                "                    ",
                "        ",
                "                    ",
                "N",
                "                                                            ",
                "      ",
                "@        ",
                str(
                    partner.invoice_ids[0].partner_id.street
                    if partner.invoice_ids
                    else partner.street or ""
                ).ljust(38),
                str(
                    partner.invoice_ids[0].partner_id.street2
                    if partner.invoice_ids and partner.invoice_ids[0].partner_id.street2
                    else partner.street2 or ""
                ).ljust(38),
                str(
                    partner.invoice_ids[0].partner_id.state_id.name
                    if partner.invoice_ids
                    and partner.invoice_ids[0].partner_id.state_id
                    else partner.state_id.name or ""
                ).ljust(38),
                str(partner.email or "").ljust(100),
                "                            ",
                str(
                    partner.invoice_ids[0].partner_id.city
                    if partner.invoice_ids
                    else partner.city or ""
                ).ljust(26),
                "00001",
                "papier ",
                "                                                                                    ",
            ]
            content_lines.append("".join(map(str, line)))

        return "\n".join(content_lines)

    def _log_file_for_each_partner(self, partners, file):
        attachment_url = f"/web/content/{file.id}?download=true"

        for partner in partners:
            partner.message_post(
                body=Markup(
                    _(
                        "Customer Details files created: <a href='%s' target='_blank'>%s</a>"
                    )
                )
                % (attachment_url, file.name)
            )

            # ✅ FIX sudo
            partner.sudo().write({
                "is_included_in_customers_export_file": True
            })

    def _creer_fichier_clients(self, partners, suffixe=""):
        """Ecrit le fichier des clients donnes et le journalise sur chacun.

        Isole de la selection : le quotidien et les reprises produisent ainsi
        exactement le meme fichier. Une divergence entre eux passerait
        autrement inapercue, et c'est la compta qui la decouvrirait.

        Le fichier est cree sans indicateur de synchronisation : le cron
        d'envoi SFTP le prendra a son prochain passage, comme les autres.
        """
        if not partners:
            _logger.info("Export clients%s : aucun client a exporter.", suffixe and " " + suffixe)
            return self.env["ir.attachment"]

        file_content = self._get_file_content(partners)
        file_name = "Customer_Details_%s%s.txt" % (
            fields.Datetime.now().strftime("%Y-%m-%d"),
            suffixe,
        )
        file = self.env["ir.attachment"].sudo().create(
            {
                "name": file_name,
                "type": "binary",
                "datas": base64.b64encode(file_content.encode("utf-8")),
                "res_model": "res.partner",
                "mimetype": "text/plain",
                "is_customer_txt": True,
            }
        )
        self._log_file_for_each_partner(partners, file)
        _logger.info("Export clients : %s, %s client(s).", file_name, len(partners))
        return file

    def cron_generate_generate_customer_files(self):
        partners = self.search(
            [
                ("is_included_in_customers_export_file", "=", False),
                ("is_company", "=", True),
            ]
        )

        try:
            self._creer_fichier_clients(partners)
        except Exception as e:
            _logger.exception("Erreur export clients: %s", e)

    def action_generer_fichier_clients_depuis(self):
        """Reprise : les clients crees ou modifies depuis une date donnee.

        A lancer une fois. Le quotidien ne peut pas produire ce fichier : il
        ne selectionne que les clients jamais exportes
        (is_included_in_customers_export_file), et un client deja parti chez
        la compta ne repartira donc jamais, meme modifie depuis. C'est
        precisement ce qu'une reprise doit rattraper, d'ou l'abandon de ce
        critere ici au profit des seules dates.

        Le drapeau n'est pas remis a zero pour autant : le journal de chaque
        fiche garde trace des deux envois, et le quotidien continue de ne
        prendre que les nouveaux.
        """
        depuis = self._date_de_reprise_clients()
        partners = self.search(
            [
                ("is_company", "=", True),
                "|",
                ("create_date", ">=", depuis),
                ("write_date", ">=", depuis),
            ]
        )
        # Pas de try/except ici, a la difference du cron : une reprise est
        # lancee a la main, celui qui la declenche doit voir l'erreur plutot
        # que la retrouver dans les journaux du serveur.
        fichier = self._creer_fichier_clients(partners, suffixe="_reprise")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "sticky": False,
                "message": _(
                    "%(nb)s client(s) exporte(s) depuis le %(date)s. "
                    "Fichier : %(fichier)s",
                    nb=len(partners),
                    date=fields.Date.to_string(fields.Date.to_date(depuis)),
                    fichier=fichier.name if fichier else "-",
                ),
            },
        }

    def _date_de_reprise_clients(self):
        """Point de depart de la reprise.

        Parametre systeme plutot que constante : rejouer une autre periode ne
        doit pas demander un deploiement.
        """
        valeur = self.env["ir.config_parameter"].sudo().get_param(
            "fma_customer_export.reprise_depuis", DEFAUT_REPRISE_DEPUIS
        )
        depuis = fields.Date.to_date(valeur)
        if not depuis:
            raise UserError(
                _(
                    "Le parametre « fma_customer_export.reprise_depuis » vaut "
                    "« %s », qui n'est pas une date. Attendu : AAAA-MM-JJ.",
                    valeur,
                )
            )
        return fields.Datetime.to_datetime(depuis)

    def cron_send_customers_file_to_sftp_server(self):
        # ✅ FIX sudo
        attachments = self.env["ir.attachment"].sudo().search(
            [
                ("res_model", "=", "res.partner"),
                ("is_customer_txt", "=", True),
                ("is_synced_to_sftp", "=", False),
            ]
        )

        get_param = self.env["ir.config_parameter"].sudo().get_param

        sftp_server_host = get_param("fma_customer_export.sftp_server_host")
        sftp_server_username = get_param("fma_customer_export.sftp_server_username")
        sftp_server_password = get_param("fma_customer_export.sftp_server_password")
        sftp_server_file_path = get_param("fma_customer_export.sftp_server_file_path")

        if not all([
            sftp_server_host,
            sftp_server_username,
            sftp_server_password,
            sftp_server_file_path,
        ]):
            _logger.error("Paramètres SFTP manquants")
            return

        for attachment in attachments:
            try:
                with self.env.cr.savepoint():
                    self._sync_file(
                        attachment,
                        sftp_server_host,
                        sftp_server_username,
                        sftp_server_password,
                        sftp_server_file_path,
                    )

                    attachment.sudo().write({
                        "is_synced_to_sftp": True
                    })

            except Exception as e:
                _logger.error("Erreur SFTP: %s", e)

    def _sync_file(
        self,
        attachment,
        sftp_server_host,
        sftp_server_username,
        sftp_server_password,
        sftp_server_file_path,
    ):
        attachment_content = base64.b64decode(attachment.datas)

        try:
            transport = paramiko.Transport((sftp_server_host, 22))
            transport.connect(
                username=sftp_server_username,
                password=sftp_server_password
            )

            sftp = paramiko.SFTPClient.from_transport(transport)
            sftp.chdir(sftp_server_file_path)

            with io.BytesIO(attachment_content) as file_obj:
                sftp.putfo(file_obj, attachment.name)

        finally:
            if "sftp" in locals():
                sftp.close()
            if "transport" in locals():
                transport.close()
