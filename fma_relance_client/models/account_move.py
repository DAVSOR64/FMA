# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.tools import format_date, formatLang
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Modele de relance a utiliser quand account_followup n'est pas installe, ou
# que ses niveaux ne portent pas de modele. Attend l'identifiant XML d'un
# mail.template, par exemple « account_followup.email_template_followup_1 ».
PARAM_MODELE = "fma_relance_client.mail_template"

# Le modele de relance en place chez FMA. Resolu par son nom : voir
# _fma_modele_relance.
NOM_MODELE = "Rappel de paiement"


class AccountMove(models.Model):
    _inherit = "account.move"

    # Le projet ne vit pas sur la facture : il se lit sur la commande a
    # l'origine des lignes. Stocke, sans quoi la colonne ne serait ni
    # filtrable, ni groupable, ni triable — c'est tout l'interet de
    # l'afficher dans une liste de relance.
    fma_project_id = fields.Many2one(
        "project.project",
        string="Projet",
        compute="_compute_fma_project_id",
        store=True,
        index="btree_not_null",
    )

    @api.depends("line_ids.sale_line_ids.order_id.project_id")
    def _compute_fma_project_id(self):
        for facture in self:
            projets = facture.line_ids.sale_line_ids.order_id.project_id
            # Une facture peut regrouper plusieurs commandes. On ne retient un
            # projet que s'il est unique : afficher le premier venu ferait
            # croire a un rattachement qui n'existe pas.
            facture.fma_project_id = projets if len(projets) == 1 else False

    # -------------------------------------------------------------------------
    # Relance sur une selection de factures
    # -------------------------------------------------------------------------

    def _fma_modele_relance(self, partenaire):
        """Le modele de mail des relances de paiement : « Rappel de paiement ».

        Cherche par son NOM et non par un identifiant XML : celui-ci depend du
        module qui livre le modele, et un modele retouche ou recree depuis
        l'interface n'en a pas. Le nom, lui, est ce que le metier connait.

        Ordre : le parametre systeme d'abord, pour qu'on puisse en imposer un
        autre sans toucher au code ; le modele nomme ensuite ; le niveau de
        relance en dernier recours, si le nom venait a changer.
        """
        Modele = self.env["mail.template"].sudo()

        reference = self.env["ir.config_parameter"].sudo().get_param(PARAM_MODELE)
        if reference:
            modele = self.env.ref(reference, raise_if_not_found=False)
            if not modele:
                modele = Modele.search([("name", "=", reference)], limit=1)
            if modele:
                return modele

        modele = Modele.search([("name", "=", NOM_MODELE)], limit=1)
        if modele:
            return modele
        # Le nom peut porter un suffixe (niveau, societe) : on elargit avant
        # d'abandonner, plutot que d'echouer sur un libelle presque juste.
        modele = Modele.search([("name", "ilike", NOM_MODELE)], limit=1)
        if modele:
            return modele

        # account_followup est une application Enterprise : elle peut ne pas
        # etre installee. On l'interroge par le registre plutot que par un
        # import, qui empecherait le module de se charger sans elle.
        if "account_followup.followup.line" in self.env:
            niveau = partenaire.followup_line_id if "followup_line_id" in partenaire._fields else False
            if not niveau:
                # Client pas encore engage dans un cycle de relance : on prend
                # le premier niveau, celui du premier rappel.
                niveau = self.env["account_followup.followup.line"].sudo().search(
                    [("company_id", "in", (False, self.env.company.id))],
                    order="delay asc", limit=1,
                )
            if niveau and niveau.mail_template_id:
                return niveau.mail_template_id

        raise UserError(_(
            "Le modele d'e-mail « %(nom)s » est introuvable.\n\n"
            "Verifiez son nom dans Parametres > Technique > Modeles d'e-mail, "
            "ou designez-en un autre dans le parametre systeme « %(param)s », "
            "qui accepte un nom de modele ou un identifiant XML.",
            nom=NOM_MODELE, param=PARAM_MODELE,
        ))

    def _fma_pieces_jointes(self, factures):
        """Les factures selectionnees, en piece jointe de la relance."""
        pdf, _type = self.env["ir.actions.report"].sudo()._render_qweb_pdf(
            "account.account_invoices", factures.ids,
        )
        piece = self.env["ir.attachment"].create({
            "name": _("Factures a regler.pdf"),
            "type": "binary",
            "raw": pdf,
            "mimetype": "application/pdf",
            "res_model": "res.partner",
            "res_id": factures[0].commercial_partner_id.id,
        })
        return piece.ids

    def _fma_recapitulatif(self, factures):
        """Le detail des factures relancees, ajoute au corps du mail.

        Sert quand le modele est ecrit sur la facture : son corps ne peut
        alors parler que d'une seule d'entre elles, alors que la relance en
        couvre plusieurs.
        """
        lignes = []
        total = 0.0
        for facture in factures.sorted(lambda f: f.invoice_date_due or f.invoice_date or fields.Date.today()):
            total += facture.amount_residual
            lignes.append(
                "<tr>"
                "<td style='padding:4px 12px 4px 0'>%s</td>"
                "<td style='padding:4px 12px 4px 0'>%s</td>"
                "<td style='padding:4px 0;text-align:right'>%s</td>"
                "</tr>" % (
                    facture.name or "",
                    format_date(self.env, facture.invoice_date_due) if facture.invoice_date_due else "",
                    formatLang(self.env, facture.amount_residual, currency_obj=facture.currency_id),
                )
            )
        return (
            "<p style='margin-top:16px'><strong>%s</strong></p>"
            "<table style='border-collapse:collapse'>"
            "<tr><th style='text-align:left;padding-right:12px'>%s</th>"
            "<th style='text-align:left;padding-right:12px'>%s</th>"
            "<th style='text-align:right'>%s</th></tr>"
            "%s"
            "<tr><td colspan='2' style='padding-top:8px'><strong>%s</strong></td>"
            "<td style='padding-top:8px;text-align:right'><strong>%s</strong></td></tr>"
            "</table>" % (
                _("Factures concernees"),
                _("Facture"), _("Echeance"), _("Reste du"),
                "".join(lignes),
                _("Total"),
                formatLang(self.env, total, currency_obj=factures[0].currency_id),
            )
        )

    def action_fma_relancer_client(self):
        """Relance chaque client des factures selectionnees.

        Un envoi par client et non par facture : relancer trois fois le meme
        client pour trois factures echues serait recu comme une maladresse.
        Les factures d'un meme client partent donc ensemble, en une piece
        jointe unique.
        """
        factures = self.filtered(lambda f: f.move_type in ("out_invoice", "out_refund"))
        if not factures:
            raise UserError(_("Selectionnez des factures client."))

        non_reglees = factures.filtered(
            lambda f: f.state == "posted" and f.payment_state not in ("paid", "reversed")
        )
        if not non_reglees:
            raise UserError(_(
                "Les factures selectionnees sont soit non comptabilisees, "
                "soit deja reglees : il n'y a rien a relancer."
            ))

        envois = 0
        for partenaire, lot in non_reglees.grouped("commercial_partner_id").items():
            modele = self._fma_modele_relance(partenaire)

            # Un modele se rend sur le modele de donnees pour lequel il a ete
            # ecrit : ses expressions parlent d'« object ». Ecrit sur le
            # client, il le prend pour cible ; ecrit sur la facture, il faut
            # lui en donner une — la plus ancienne echeance, celle qui motive
            # la relance.
            if modele.model_id.model == "account.move":
                cible = min(lot, key=lambda f: f.invoice_date_due or f.invoice_date or fields.Date.today())
                cible_id = cible.id
                # Le corps ne parle alors que de cette facture-la : on lui
                # ajoute le detail des autres, sans quoi le client recevrait
                # une relance qui en passe sous silence une partie.
                recapitulatif = self._fma_recapitulatif(lot) if len(lot) > 1 else ""
            else:
                cible_id = partenaire.id
                # Un modele ecrit sur le client enumere deja ses factures dues.
                recapitulatif = ""

            valeurs = {}
            rendu = modele.generate_email(cible_id, ["body_html"])
            corps_mail = (rendu.get("body_html") or "") + recapitulatif
            if corps_mail:
                valeurs["body_html"] = corps_mail

            pieces = self._fma_pieces_jointes(lot)
            if pieces:
                valeurs["attachment_ids"] = [(6, 0, pieces)]

            modele.send_mail(cible_id, force_send=True, email_values=valeurs or None)

            # Trace dans le suivi de chaque facture : c'est la qu'on cherchera
            # si le client conteste avoir ete relance. message_post travaille
            # sur un enregistrement a la fois, d'ou la boucle.
            corps = _(
                "Relance envoyee a %(client)s (modele « %(modele)s »), "
                "portant sur %(nb)s facture(s).",
                client=partenaire.display_name, modele=modele.name, nb=len(lot),
            )
            for facture in lot:
                facture.message_post(body=corps)
            envois += 1

        ignorees = len(factures) - len(non_reglees)
        message = _("%s relance(s) envoyee(s).", envois)
        if ignorees:
            message += _(" %s facture(s) ignoree(s) : deja reglee ou non comptabilisee.", ignorees)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"type": "success", "message": message, "sticky": False},
        }
