# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.tools import format_date, formatLang
from odoo.exceptions import UserError
from markupsafe import Markup

_logger = logging.getLogger(__name__)

# Trois relances : au-dela, le dossier n'est plus une affaire de rappel.
NB_NIVEAUX = 3

# Modele impose, par niveau : « fma_relance_client.mail_template_1 », etc.
# Accepte un nom de modele ou un identifiant XML. Ne sert que si les niveaux
# de relance natifs ne portent pas de modele.
PARAM_MODELE = "fma_relance_client.mail_template_%s"

# Modele de dernier recours, tous niveaux confondus. Resolu par son nom : voir
# _fma_modele_relance.
NOM_MODELE = "Rappel de paiement"

# Utilisateur charge du recouvrement, a qui les activites sont affectees.
# Accepte un identifiant numerique ou un login.
PARAM_RESPONSABLE = "fma_relance_client.responsable"


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

    # Les trois dates sont la memoire des relances. Elles ne sont pas saisies :
    # chaque envoi remplit la premiere encore vide. copy=False, sinon dupliquer
    # une facture ferait croire qu'elle a deja ete relancee.
    fma_date_relance_1 = fields.Date(string="Date relance 1", readonly=True, copy=False)
    fma_date_relance_2 = fields.Date(string="Date relance 2", readonly=True, copy=False)
    fma_date_relance_3 = fields.Date(string="Date relance 3", readonly=True, copy=False)

    # Le niveau de la PROCHAINE relance, c'est-a-dire le modele de mail qui
    # partira. Stocke : c'est sur lui qu'on filtre pour savoir qui relancer.
    fma_niveau_relance = fields.Integer(
        string="Niveau de relance",
        compute="_compute_fma_niveau_relance",
        store=True,
        help="Niveau du prochain rappel, deduit des dates deja renseignees. "
             "Vaut %s au maximum." % NB_NIVEAUX,
    )

    @api.depends("line_ids.sale_line_ids.order_id.project_id")
    def _compute_fma_project_id(self):
        for facture in self:
            projets = facture.line_ids.sale_line_ids.order_id.project_id
            # Une facture peut regrouper plusieurs commandes. On ne retient un
            # projet que s'il est unique : afficher le premier venu ferait
            # croire a un rattachement qui n'existe pas.
            facture.fma_project_id = projets if len(projets) == 1 else False

    @api.depends("fma_date_relance_1", "fma_date_relance_2", "fma_date_relance_3")
    def _compute_fma_niveau_relance(self):
        for facture in self:
            envoyees = len(facture._fma_dates_relance(remplies=True))
            # Plafonne au dernier niveau : passe trois rappels, on continue de
            # relancer avec le dernier modele plutot que de s'arreter, mais il
            # n'y a plus de colonne pour en garder la date.
            facture.fma_niveau_relance = min(envoyees + 1, NB_NIVEAUX)

    def _fma_dates_relance(self, remplies=False):
        """Les champs de date de relance, dans l'ordre des niveaux."""
        noms = ["fma_date_relance_%s" % n for n in range(1, NB_NIVEAUX + 1)]
        if remplies:
            return [n for n in noms if self[n]]
        return noms

    # -------------------------------------------------------------------------
    # Choix du modele de mail
    # -------------------------------------------------------------------------

    @api.model
    def _fma_niveaux_natifs(self):
        """Les niveaux de relance d'Odoo, du premier rappel au dernier.

        account_followup est une application Enterprise : elle peut ne pas etre
        installee. On l'interroge par le registre plutot que par un import, qui
        empecherait le module de se charger sans elle.
        """
        if "account_followup.followup.line" not in self.env:
            return self.env["mail.template"].browse()
        return self.env["account_followup.followup.line"].sudo().search(
            [("company_id", "in", (False, self.env.company.id))], order="delay asc"
        )

    def _fma_modele_relance(self, niveau):
        """Le modele de mail du niveau demande.

        Le niveau vient des colonnes de dates, le modele vient d'Odoo : c'est
        la configuration des niveaux de relance qui decide de ce qui est ecrit
        au client, pas ce module. Un troisieme rappel n'a pas le ton du
        premier, et ce ton se regle dans l'interface, sans deploiement.

        Ordre : le parametre systeme du niveau d'abord, pour pouvoir en imposer
        un ; le niveau natif correspondant ensuite ; le modele NOM_MODELE en
        dernier recours, si les niveaux ne sont pas configures.
        """
        Modele = self.env["mail.template"].sudo()

        reference = self.env["ir.config_parameter"].sudo().get_param(PARAM_MODELE % niveau)
        if reference:
            modele = self.env.ref(reference, raise_if_not_found=False)
            if not modele:
                modele = Modele.search([("name", "=", reference)], limit=1)
            if modele:
                return modele

        niveaux = self._fma_niveaux_natifs()
        if niveaux:
            # Moins de niveaux configures que de colonnes : on reste sur le
            # dernier plutot que de sortir de la liste.
            ligne = niveaux[min(niveau, len(niveaux)) - 1]
            if ligne.mail_template_id:
                return ligne.mail_template_id

        modele = Modele.search([("name", "=", NOM_MODELE)], limit=1)
        if modele:
            return modele
        # Le nom peut porter un suffixe (niveau, societe) : on elargit avant
        # d'abandonner, plutot que d'echouer sur un libelle presque juste.
        modele = Modele.search([("name", "ilike", NOM_MODELE)], limit=1)
        if modele:
            return modele

        raise UserError(_(
            "Aucun modele de relance pour le niveau %(niveau)s.\n\n"
            "Renseignez un modele d'e-mail sur les niveaux de relance "
            "(Comptabilite > Configuration > Niveaux de relance), ou a defaut "
            "le parametre systeme « %(param)s », qui accepte un nom de modele "
            "ou un identifiant XML.",
            niveau=niveau, param=PARAM_MODELE % niveau,
        ))

    # -------------------------------------------------------------------------
    # Corps du mail
    # -------------------------------------------------------------------------

    def _fma_corps_rendu(self, modele, res_id):
        """Le corps du modele, rendu, pour pouvoir y ajouter le detail.

        generate_email a disparu de mail.template en Odoo 19 : le rendu passe
        par _render_field, du mixin de rendu. On renvoie None plutot que de
        laisser remonter une erreur — mieux vaut une relance sans le detail des
        autres factures qu'une relance qui ne part pas.
        """
        try:
            return modele._render_field("body_html", [res_id])[res_id]
        except Exception:
            _logger.warning(
                "Relance : corps du modele « %s » non rendu, envoi sans le "
                "recapitulatif des factures.", modele.name, exc_info=True,
            )
            return None

    def _fma_recapitulatif(self, factures):
        """Le detail des factures relancees, ajoute au corps du mail.

        Renvoie du Markup et non une chaine : _render_field rend du Markup, et
        « Markup + str » echappe la chaine au lieu de la concatener. Le tableau
        arrivait donc en fin de message sous forme de balises en clair.

        Les valeurs, elles, sont echappees une a une : un numero de facture ou
        un libelle de devise ne doit pas pouvoir injecter de balise.
        """
        lignes = Markup("")
        total = 0.0
        ligne = Markup(
            "<tr>"
            "<td style='padding:4px 12px 4px 0'>%s</td>"
            "<td style='padding:4px 12px 4px 0'>%s</td>"
            "<td style='padding:4px 0;text-align:right'>%s</td>"
            "</tr>"
        )
        for facture in factures.sorted(lambda f: f.invoice_date_due or f.invoice_date or fields.Date.today()):
            total += facture.amount_residual
            lignes += ligne % (
                facture.name or "",
                format_date(self.env, facture.invoice_date_due) if facture.invoice_date_due else "",
                formatLang(self.env, facture.amount_residual, currency_obj=facture.currency_id),
            )
        entete = Markup(
            "<p style='margin-top:16px'><strong>%s</strong></p>"
            "<table style='border-collapse:collapse'>"
            "<tr><th style='text-align:left;padding-right:12px'>%s</th>"
            "<th style='text-align:left;padding-right:12px'>%s</th>"
            "<th style='text-align:right'>%s</th></tr>"
        ) % (_("Factures concernees"), _("Facture"), _("Echeance"), _("Reste du"))
        pied = Markup(
            "<tr><td colspan='2' style='padding-top:8px'><strong>%s</strong></td>"
            "<td style='padding-top:8px;text-align:right'><strong>%s</strong></td></tr>"
            "</table>"
        ) % (_("Total"), formatLang(self.env, total, currency_obj=factures[0].currency_id))
        return entete + lignes + pied

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

    # -------------------------------------------------------------------------
    # Envoi
    # -------------------------------------------------------------------------

    @api.model
    def _fma_domaine_a_relancer(self):
        """Les factures client qui appellent une relance."""
        return [
            ("move_type", "in", ("out_invoice", "out_refund")),
            ("state", "=", "posted"),
            ("payment_state", "not in", ("paid", "reversed", "invoicing_legacy")),
            ("invoice_date_due", "<", fields.Date.context_today(self)),
        ]

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
            lambda f: f.state == "posted"
            and f.payment_state not in ("paid", "reversed", "invoicing_legacy")
        )
        if not non_reglees:
            raise UserError(_(
                "Les factures selectionnees sont soit non comptabilisees, "
                "soit deja reglees : il n'y a rien a relancer."
            ))

        envois = 0
        for partenaire, lot in non_reglees.grouped("commercial_partner_id").items():
            # Le niveau du client est celui de sa facture la plus relancee :
            # c'est l'anciennete du retard qui donne son ton au message, pas la
            # derniere facture emise.
            niveau = max(lot.mapped("fma_niveau_relance") or [1])
            modele = self._fma_modele_relance(niveau)

            # Un modele se rend sur le modele de donnees pour lequel il a ete
            # ecrit : ses expressions parlent d'« object ». Ecrit sur le
            # client, il le prend pour cible ; ecrit sur la facture, il faut
            # lui en donner une — la plus ancienne echeance, celle qui motive
            # la relance.
            if modele.model_id.model == "account.move":
                cible = min(lot, key=lambda f: f.invoice_date_due or f.invoice_date or fields.Date.today())
                cible_id = cible.id
            else:
                cible_id = partenaire.id
            # Le detail des factures selectionnees est ajoute des qu'il y en a
            # plusieurs, y compris derriere un modele ecrit sur le client : ce
            # dernier enumere les factures selon SES criteres de relance, pas
            # selon la selection. Un client relance sur deux factures dont une
            # seule remonte au modele recevrait un rappel ampute.
            recapitulatif = self._fma_recapitulatif(lot) if len(lot) > 1 else ""

            valeurs = {}
            if recapitulatif:
                corps_rendu = self._fma_corps_rendu(modele, cible_id)
                if corps_rendu is not None:
                    valeurs["body_html"] = corps_rendu + recapitulatif

            pieces = self._fma_pieces_jointes(lot)
            if pieces:
                valeurs["attachment_ids"] = [(6, 0, pieces)]

            modele.send_mail(cible_id, force_send=True, email_values=valeurs or None)
            lot._fma_enregistrer_relance(niveau, modele, partenaire)
            self._fma_avancer_suivi_natif(partenaire, niveau)
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

    def _fma_enregistrer_relance(self, niveau, modele, partenaire):
        """Date la relance sur chaque facture et la trace dans son suivi.

        Chaque facture avance d'un cran, meme si le mail est parti au niveau du
        lot : c'est bien elle qui vient d'etre reclamee.
        """
        aujourdhui = fields.Date.context_today(self)
        for facture in self:
            vides = [n for n in facture._fma_dates_relance() if not facture[n]]
            if vides:
                facture.sudo().write({vides[0]: aujourdhui})
                rang = facture._fma_dates_relance().index(vides[0]) + 1
                trace = _(
                    "Relance %(rang)s envoyee a %(client)s (modele « %(modele)s »), "
                    "portant sur %(nb)s facture(s).",
                    rang=rang, client=partenaire.display_name,
                    modele=modele.name, nb=len(self),
                )
            else:
                # Les trois colonnes sont prises : on relance quand meme, mais
                # il n'y a plus de case pour en garder la date.
                trace = _(
                    "Relance supplementaire envoyee a %(client)s (modele "
                    "« %(modele)s ») — les %(nb)s dates de relance sont deja "
                    "renseignees.",
                    client=partenaire.display_name, modele=modele.name, nb=NB_NIVEAUX,
                )
            # message_post travaille sur un enregistrement a la fois.
            facture.message_post(body=trace)

    # -------------------------------------------------------------------------
    # Activite quotidienne du recouvrement
    # -------------------------------------------------------------------------

    @api.model
    def _fma_responsable_relance(self, partenaire=None):
        """L'utilisateur charge du recouvrement pour ce client.

        Le champ « Responsable » du bloc Suivi des factures d'abord : c'est la
        qu'Odoo le range, c'est la que le metier le saisit, et il peut differer
        d'un client a l'autre. Le parametre systeme ne sert que de defaut
        commun, pour les clients ou rien n'est renseigne.
        """
        if partenaire is not None and "followup_responsible_id" in partenaire._fields:
            responsable = partenaire.followup_responsible_id
            if responsable:
                return responsable

        valeur = self.env["ir.config_parameter"].sudo().get_param(PARAM_RESPONSABLE)
        if not valeur:
            return self.env["res.users"].browse()
        Utilisateur = self.env["res.users"].sudo()
        if str(valeur).isdigit():
            return Utilisateur.browse(int(valeur)).exists()
        return Utilisateur.search([("login", "=", valeur)], limit=1)

    def _fma_avancer_suivi_natif(self, partenaire, niveau):
        """Fait avancer le suivi des factures d'Odoo apres l'envoi.

        Sans cela, la frise « Premier email de rappel / Deuxieme rappel » de la
        fiche client reste au premier cran quel que soit le nombre de relances
        envoyees : nos colonnes avancent, l'ecran natif non, et les deux se
        contredisent sous les yeux du comptable.

        Chaque nom de champ est verifie avant d'etre ecrit : ce sont ceux d'un
        module Enterprise, qu'on ne peut pas relire ici.
        """
        champs = partenaire._fields
        if "followup_line_id" not in champs:
            return
        niveaux = self._fma_niveaux_natifs()
        if not niveaux:
            return

        rang = min(niveau, len(niveaux)) - 1
        valeurs = {"followup_line_id": niveaux[rang].id}

        # Prochaine echeance : l'ecart de delai entre le niveau atteint et le
        # suivant. Au dernier niveau il n'y a plus d'apres, on n'y touche pas.
        if "followup_next_action_date" in champs and rang + 1 < len(niveaux):
            ecart = (niveaux[rang + 1].delay or 0) - (niveaux[rang].delay or 0)
            valeurs["followup_next_action_date"] = fields.Date.add(
                fields.Date.context_today(self), days=max(ecart, 1)
            )
        partenaire.sudo().write(valeurs)

    @api.model
    def cron_fma_activites_relance(self):
        """Pose chaque jour au recouvrement les clients a relancer.

        Une activite par client, et non une seule qui les listerait tous : une
        activite se marque faite d'un bloc. Celui qui a relance trois clients
        sur quarante ne pourrait pas le noter, et le lendemain la meme liste
        reviendrait sans distinguer ce qui a ete traite.

        Les clients qui portent deja une activite de relance ouverte sont
        laisses de cote : le cron passe tous les jours, il n'a pas a empiler
        des rappels sur un travail en cours.
        """
        factures = self.sudo().search(self._fma_domaine_a_relancer())
        if not factures:
            _logger.info("Relance : aucune facture echue a relancer.")
            return True

        type_activite = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        Activite = self.env["mail.activity"].sudo()
        modele_partenaire = self.env["ir.model"]._get("res.partner").id
        creees = 0

        for partenaire, lot in factures.grouped("commercial_partner_id").items():
            responsable = self._fma_responsable_relance(partenaire)
            if not responsable:
                _logger.warning(
                    "Relance : pas de responsable pour %s, ni sur la fiche ni "
                    "dans le parametre « %s » — client passe.",
                    partenaire.display_name, PARAM_RESPONSABLE,
                )
                continue
            deja = Activite.search_count([
                ("res_model", "=", "res.partner"),
                ("res_id", "=", partenaire.id),
                ("user_id", "=", responsable.id),
                ("summary", "=like", "Relance client%"),
            ])
            if deja:
                continue

            niveau = max(lot.mapped("fma_niveau_relance") or [1])
            du = sum(lot.mapped("amount_residual"))
            valeurs = {
                "res_model_id": modele_partenaire,
                "res_id": partenaire.id,
                "user_id": responsable.id,
                "date_deadline": fields.Date.context_today(self),
                "summary": _("Relance client niveau %s", niveau),
                "note": _(
                    "%(nb)s facture(s) echue(s), %(montant)s restant du.",
                    nb=len(lot),
                    montant=formatLang(self.env, du, currency_obj=lot[0].currency_id),
                ),
            }
            if type_activite:
                valeurs["activity_type_id"] = type_activite.id
            Activite.create(valeurs)
            creees += 1

        _logger.info("Relance : %s activite(s) creee(s).", creees)
        return True
