# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Modele de relance a utiliser quand account_followup n'est pas installe, ou
# que ses niveaux ne portent pas de modele. Attend l'identifiant XML d'un
# mail.template, par exemple « account_followup.email_template_followup_1 ».
PARAM_MODELE = "fma_relance_client.mail_template"


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
        """Le modele de mail des relances de paiement.

        On ne redefinit pas de modele : la demande est de relancer « avec le
        meme modele que les relances de paiement ». Il est donc pris la ou il
        est deja configure, dans les niveaux de relance, et le parametre
        systeme ne sert que de recours.
        """
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

        reference = self.env["ir.config_parameter"].sudo().get_param(PARAM_MODELE)
        if reference:
            modele = self.env.ref(reference, raise_if_not_found=False)
            if modele:
                return modele

        raise UserError(_(
            "Aucun modele de relance n'est configure.\n\n"
            "Renseignez-le sur un niveau de relance (Comptabilite > "
            "Configuration > Niveaux de relance), ou a defaut dans le "
            "parametre systeme « %s », qui attend l'identifiant XML d'un "
            "modele d'e-mail.", PARAM_MODELE,
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
            valeurs = {}
            pieces = self._fma_pieces_jointes(lot)
            if pieces:
                valeurs["attachment_ids"] = [(6, 0, pieces)]
            modele.send_mail(
                partenaire.id,
                force_send=True,
                email_values=valeurs or None,
            )
            # Trace dans le suivi de chaque facture : c'est la qu'on cherchera
            # si le client conteste avoir ete relance. message_post travaille
            # sur un enregistrement a la fois, d'ou la boucle.
            corps = _(
                "Relance envoyee a %(client)s (modele « %(modele)s »).",
                client=partenaire.display_name, modele=modele.name,
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
