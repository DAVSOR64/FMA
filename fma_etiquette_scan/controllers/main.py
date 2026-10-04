# -*- coding: utf-8 -*-
"""Page SAV ouverte par le QR code de l'etiquette.

Une seule adresse, /fma/sav/<jeton>, et deux publics :

* un utilisateur interne connecte voit la fiche complete de la menuiserie,
  ses tickets, et declare en son nom ;
* quelqu'un qui n'a pas de compte — le poseur, le client final sur le
  chantier — voit le strict necessaire pour reconnaitre la menuiserie et un
  formulaire de declaration. Ni client, ni affaire, ni prix.

Le jeton est aleatoire (32 caracteres hexadecimaux) : connaitre un numero
de serie ne suffit pas a ouvrir la page d'une autre menuiserie. Le parametre
systeme fma_etiquette_scan.sav_public = 0 ferme l'acces sans connexion.
"""
import logging

from odoo import _, http
from odoo.http import request

_logger = logging.getLogger(__name__)

TAILLE_MAX = 4000


class FmaSav(http.Controller):

    def _serie(self, token):
        if not token or len(token) < 16:
            return request.env["stock.lot"].sudo().browse()
        return request.env["stock.lot"].sudo().search(
            [("fma_sav_token", "=", token.lower())], limit=1)

    def _interne(self):
        return request.env.user._is_internal()

    def _public_autorise(self):
        return request.env["ir.config_parameter"].sudo().get_param(
            "fma_etiquette_scan.sav_public", "1") not in ("0", "False", "")

    def _valeurs(self, serie, **extra):
        interne = self._interne()
        valeurs = {
            "serie": serie,
            "interne": interne,
            "repere": serie._fma_repere(),
            "dimensions": serie._fma_dimensions(),
            "tickets": serie.fma_ticket_ids.sorted("id", reverse=True)
            if interne else serie.fma_ticket_ids.browse(),
            "action_tickets": "fma_etiquette_scan.action_fma_ticket_sav",
            "erreur": "",
            "saisie": {},
        }
        valeurs.update(extra)
        return valeurs

    @http.route("/fma/sav/<string:token>", type="http", auth="public",
                methods=["GET"], sitemap=False)
    def sav(self, token, **kw):
        serie = self._serie(token)
        if not serie:
            return request.render(
                "fma_etiquette_scan.sav_introuvable", {}, status=404)
        if not self._interne() and not self._public_autorise():
            return request.redirect(
                "/web/login?redirect=/fma/sav/%s" % token)
        return request.render(
            "fma_etiquette_scan.sav_page", self._valeurs(serie))

    @http.route("/fma/sav/<string:token>/declarer", type="http",
                auth="public", methods=["POST"], csrf=True, sitemap=False)
    def sav_declarer(self, token, **post):
        serie = self._serie(token)
        if not serie:
            return request.render(
                "fma_etiquette_scan.sav_introuvable", {}, status=404)
        interne = self._interne()
        if not interne and not self._public_autorise():
            return request.redirect(
                "/web/login?redirect=/fma/sav/%s" % token)

        def champ(nom, taille=200):
            return (post.get(nom) or "").strip()[:taille]

        objet = champ("objet")
        description = champ("description", TAILLE_MAX)
        nom, email, telephone = champ("nom"), champ("email"), champ("telephone")

        # Champ piege, invisible pour une personne : un robot le remplit.
        # On repond comme si tout s'etait bien passe, sans rien creer.
        if champ("site_web"):
            return request.render("fma_etiquette_scan.sav_merci", {
                "serie": serie, "reference": "", "interne": False,
                "lien": ""})

        if not description or (not interne and not (nom and (email or telephone))):
            return request.render(
                "fma_etiquette_scan.sav_page",
                self._valeurs(
                    serie,
                    erreur=_(
                        "Décrivez le problème, et laissez votre nom avec un "
                        "e-mail ou un téléphone pour que nous puissions "
                        "vous rappeler.") if not interne else _(
                        "Décrivez le problème."),
                    saisie=post))

        Ticket = request.env["helpdesk.ticket"]
        extra = {}
        if interne:
            client = serie._fma_contexte()["client"]
            if client:
                extra["partner_id"] = client.id
            createur = serie.with_env(request.env)
        else:
            # Le declarant n'est pas forcement le client de la commande :
            # on ne rattache pas le ticket a ce dernier, on note qui appelle.
            description = "%s\n\n%s" % (description, _(
                "Déclaré par %(nom)s — %(email)s %(tel)s (formulaire de "
                "l'étiquette)", nom=nom, email=email, tel=telephone))
            for cle, valeur in (("partner_name", nom),
                                ("partner_email", email),
                                ("partner_phone", telephone)):
                if valeur and cle in Ticket._fields:
                    extra[cle] = valeur
            createur = serie.sudo()
        ticket = createur._fma_creer_ticket(objet, description, extra)
        reference = (
            ticket.sudo().ticket_ref
            if "ticket_ref" in ticket._fields else "") or str(ticket.id)
        return request.render("fma_etiquette_scan.sav_merci", {
            "serie": serie,
            "reference": reference,
            "interne": interne,
            "lien": "/odoo/action-fma_etiquette_scan.action_fma_ticket_sav/%s"
            % ticket.id,
        })
