import json
import logging
from datetime import timedelta

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HubspotExportLog(models.Model):
    _name = "hubspot.export.log"
    _description = "Journal export HubSpot"
    _order = "create_date desc"

    name = fields.Char(required=True)
    export_type = fields.Selection(
        [("entreprises", "Entreprises"), ("quotes", "Chiffrages / Devis")],
        required=True,
    )
    status = fields.Selection(
        [("success", "Succès"), ("error", "Erreur")],
        required=True,
        default="success",
    )
    record_count = fields.Integer(string="Nombre d'enregistrements")
    response_code = fields.Integer(string="Code réponse HTTP")
    message = fields.Text()
    payload_preview = fields.Text(string="Aperçu JSON")


class HubspotWebhookExport(models.AbstractModel):
    _name = "hubspot.webhook.export"
    _description = "Export Webhook HubSpot / n8n"

    # -------------------------------------------------------------------------
    # Public actions
    # -------------------------------------------------------------------------

    @api.model
    def action_export_entreprises(self, force_full=False):
        payload = self._prepare_entreprises_payload(force_full=force_full)
        return self._post_payload("entreprises", payload)

    @api.model
    def action_export_quotes(self, force_full=False):
        payload = self._prepare_quotes_payload(force_full=force_full)
        return self._post_payload("quotes", payload)

    @api.model
    def _taille_de_lot(self):
        """Nombre d'enregistrements par envoi. 500 par defaut, parametrable."""
        valeur = self.env["ir.config_parameter"].sudo().get_param(
            "hubspot_export.batch_size", "500"
        )
        try:
            taille = int(valeur)
        except (TypeError, ValueError):
            taille = 500
        return taille if taille > 0 else 500

    @api.model
    def _envoyer_par_lots(self, export_type, cle, enregistrements):
        """Decoupe la charge et l'envoie lot par lot.

        Un envoi unique de plusieurs milliers de fiches expose a trois
        ennuis : le delai d'attente du webhook, la limite de taille du corps
        de requete, et surtout le tout ou rien — une erreur en fin de
        traitement perdait l'integralite de l'envoi. Par lots, ce qui est
        passe reste passe, et le journal indique precisement ou l'envoi s'est
        arrete.

        Chaque lot porte son rang et le total, pour que le destinataire sache
        qu'il recoit une serie et puisse detecter un trou.
        """
        taille = self._taille_de_lot()
        total = len(enregistrements)
        if not total:
            self._post_payload(export_type, {cle: []})
            return 0
        nb_lots = (total + taille - 1) // taille
        for rang in range(nb_lots):
            lot = enregistrements[rang * taille:(rang + 1) * taille]
            self._post_payload(export_type, {
                cle: lot,
                "lot": rang + 1,
                "nb_lots": nb_lots,
                "total_enregistrements": total,
            })
            _logger.info(
                "HubSpot : %s, lot %s/%s envoye (%s enregistrements).",
                export_type, rang + 1, nb_lots, len(lot),
            )
        return nb_lots

    @api.model
    def action_export_entreprises_complet_par_lots(self):
        """Premier envoi : TOUTES les entreprises, par lots de 500.

        A lancer une fois, pour la reprise de l'existant. Le quotidien passe
        ensuite par cron_export_clients_du_jour.
        """
        charge = self._prepare_entreprises_payload(force_full=True)
        nb = self._envoyer_par_lots("entreprises", "entreprise", charge["entreprise"])
        _logger.info("HubSpot : envoi complet des entreprises termine, %s lot(s).", nb)
        return True

    @api.model
    def cron_export_clients_du_jour(self):
        """Clients crees ou modifies DANS LA JOURNEE.

        Le domaine part de minuit, et non des vingt-quatre dernieres heures :
        une fenetre glissante decale a chaque execution et finit par manquer
        des fiches quand le cron prend du retard, ou par les envoyer deux fois
        quand il repasse tot.

        create_date couvre les creations, write_date les modifications ; Odoo
        renseigne les deux a la creation, mais on interroge explicitement les
        deux pour rester lisible.
        """
        debut = fields.Datetime.to_datetime(fields.Date.context_today(self))
        partenaires = self.env["res.partner"].sudo().search(
            self._domaine_entreprises() + [
                "|",
                ("create_date", ">=", debut),
                ("write_date", ">=", debut),
            ]
        )
        if not partenaires:
            _logger.info("HubSpot : aucun client cree ou modifie aujourd'hui.")
            return True
        charge = self._entreprises_depuis(partenaires)
        self._envoyer_par_lots("entreprises", "entreprise", charge)
        return True

    @api.model
    def action_export_devis_complet_par_lots(self):
        """Premier envoi : TOUS les devis/commandes, par lots.

        Pendant du complet entreprises. A lancer une fois pour la reprise de
        l'historique ; le quotidien passe ensuite par cron_export_devis_du_jour.
        """
        orders = self._get_sale_orders_to_export(force_full=True)
        nb = self._envoyer_par_lots("quotes", "data", self._devis_depuis(orders))
        _logger.info("HubSpot : envoi complet des devis termine, %s lot(s).", nb)
        return True

    @api.model
    def cron_export_devis_du_jour(self):
        """Devis/commandes crees ou modifies DANS LA JOURNEE.

        Meme fenetre que pour les clients : depuis minuit, et non les vingt-
        quatre dernieres heures. Un changement d'etat, de montant ou de ligne
        touche write_date, donc un devis confirme dans la journee repart.
        """
        debut = fields.Datetime.to_datetime(fields.Date.context_today(self))
        orders = self.env["sale.order"].sudo().search([
            ("state", "in", ["draft", "sent", "sale", "done", "cancel"]),
            "|",
            ("create_date", ">=", debut),
            ("write_date", ">=", debut),
        ])
        if not orders:
            _logger.info("HubSpot : aucun devis cree ou modifie aujourd'hui.")
            return True
        self._envoyer_par_lots("quotes", "data", self._devis_depuis(orders))
        return True

    @api.model
    def action_export_complet_par_lots(self):
        """Reprise complete : entreprises puis devis/commandes."""
        self.action_export_entreprises_complet_par_lots()
        self.action_export_devis_complet_par_lots()
        return True

    @api.model
    def cron_export_du_jour(self):
        """Quotidien complet : clients puis devis/commandes de la journee."""
        self.cron_export_clients_du_jour()
        self.cron_export_devis_du_jour()
        return True

    @api.model
    def action_export_all_full(self):
        """Premier envoi complet : entreprises + devis/commandes."""
        self.action_export_entreprises(force_full=True)
        self.action_export_quotes(force_full=True)
        return True

    @api.model
    def cron_export_entreprises_and_quotes(self):
        """Export quotidien. En général : uniquement les modifications si le paramètre est coché."""
        self.action_export_entreprises()
        self.action_export_quotes()
        return True

    # Compatibilité avec l'ancienne version du module.
    @api.model
    def action_export_clients(self):
        return self.action_export_entreprises()

    @api.model
    def cron_export_clients_and_quotes(self):
        return self.cron_export_entreprises_and_quotes()

    # -------------------------------------------------------------------------
    # Payload entreprises
    # -------------------------------------------------------------------------

    @api.model
    def _entreprises_depuis(self, partners):
        """Traduit des fiches en enregistrements pour le webhook.

        Isole de la selection : l'envoi complet, l'envoi quotidien et l'envoi
        des seules modifications partagent ainsi exactement la meme mise en
        forme. Une divergence entre eux passerait autrement inapercue.
        """
        entreprises = []
        for partner in partners:
            entreprises.append({
                "odoo_id": partner.id,
                "client": partner.ref or "",
                "raison_sociale": partner.commercial_company_name or partner.name or "",
                "siret": self._get_siret(partner),
                "siren": self._get_siren(partner),
                "adresse": self._get_partner_address(partner),
                "code_postal": partner.zip or "",
                "ville": partner.city or "",
                "statut": self._get_partner_status(partner),
                "date_modification": fields.Date.to_string(partner.write_date.date()) if partner.write_date else "",
            })

        return entreprises

    @api.model
    def _prepare_entreprises_payload(self, force_full=False):
        partners = self._get_partners_to_export(force_full=force_full)
        return {"entreprise": self._entreprises_depuis(partners)}

    @api.model
    def _domaine_entreprises(self):
        """Perimetre des fiches envoyees a HubSpot.

        Societes et prospects/clients. Les contacts enfants purs sont ecartes :
        ils feraient doublon avec leur societe cote HubSpot.
        """
        return [
            ("active", "=", True),
            # SOCIETES uniquement. La version precedente disait « societe OU
            # contact sans parent », un OU qui embarquait les personnes
            # physiques independantes — un particulier, un contact cree sans
            # societe. Le commentaire annoncait pourtant l'inverse.
            ("is_company", "=", True),
            # Clients et prospects, jamais les fournisseurs purs. Le statut
            # envoye distingue ensuite les deux : customer_rank > 0 donne
            # « client », sinon « prospect ».
            "|", ("customer_rank", ">", 0), ("supplier_rank", "=", 0),
        ]

    @api.model
    def _get_partners_to_export(self, force_full=False):
        # Sociétés et prospects/clients. On évite les contacts enfants purs pour limiter les doublons.
        domain = self._domaine_entreprises()
        if self._export_only_updated() and not force_full:
            since = fields.Datetime.now() - timedelta(days=1)
            domain.append(("write_date", ">=", since))
        return self.env["res.partner"].sudo().search(domain)

    @api.model
    def _get_partner_status(self, partner):
        if partner.customer_rank and partner.customer_rank > 0:
            return "client"
        return "prospect"

    @api.model
    def _get_partner_address(self, partner):
        parts = [partner.street or "", partner.street2 or ""]
        return ", ".join([p for p in parts if p])

    # -------------------------------------------------------------------------
    # Payload devis / commandes
    # -------------------------------------------------------------------------

    @api.model
    def _prepare_quotes_payload(self, force_full=False):
        orders = self._get_sale_orders_to_export(force_full=force_full)
        return {"data": self._devis_depuis(orders)}

    @api.model
    def _devis_depuis(self, orders):
        """Traduit des devis/commandes en enregistrements pour le webhook.

        Isole de la selection, pour la meme raison que _entreprises_depuis :
        l'envoi complet, le quotidien et l'envoi des modifications doivent
        produire exactement la meme structure.
        """
        data = []

        for order in orders:
            partner = order.partner_id
            date_creation = order.create_date.date() if order.create_date else False
            date_envoi = self._get_quotation_sent_date(order)

            data.append({
                "odoo_id": partner.id,
                "Client": partner.ref or "",
                "Devis": order.name or "",
                "Commande": order.name if order.state in ["sale", "done"] else "",
                "statut_chiffrage": self._map_order_status(order),
                "statut_odoo": order.state or "",
                "Prix": order.amount_total,
                "SIRET": self._get_siret(partner),
                "SIREN": self._get_siren(partner),
                "Chantier": self._get_site_name(order),
                "Proprietaire": order.user_id.name or "",
                "Date_Creation": fields.Date.to_string(date_creation) if date_creation else "",
                "Date_Envoi": fields.Date.to_string(date_envoi) if date_envoi else "",
                # Champs conservés pour compatibilité avec la première structure reçue.
                "Activite": self._get_order_activity(order),
                "Message": "",
            })

        return data

    @api.model
    def _get_sale_orders_to_export(self, force_full=False):
        domain = [("state", "in", ["draft", "sent", "sale", "done", "cancel"])]
        if self._export_only_updated() and not force_full:
            since = fields.Datetime.now() - timedelta(days=1)
            domain.append(("write_date", ">=", since))
        return self.env["sale.order"].sudo().search(domain)

    @api.model
    def _get_quotation_sent_date(self, order):
        message = self.env["mail.message"].sudo().search([
            ("model", "=", "sale.order"),
            ("res_id", "=", order.id),
            ("message_type", "=", "email"),
        ], order="date asc", limit=1)
        return message.date.date() if message and message.date else False

    @api.model
    def _get_order_activity(self, order):
        return self._safe_get(order, "x_studio_activite") or order.note or ""

    @api.model
    def _get_site_name(self, order):
        return (
            self._safe_get(order, "x_studio_chantier")
            or self._safe_get(order, "x_studio_nom_chantier")
            or order.partner_shipping_id.display_name
            or ""
        )

    @api.model
    def _map_order_status(self, order):
        mapping = {
            "draft": "devis brouillon",
            "sent": "devis envoyé",
            "sale": "commande confirmée",
            "done": "commande terminée",
            "cancel": "annulé",
        }
        return mapping.get(order.state, order.state or "")

    # -------------------------------------------------------------------------
    # HTTP POST
    # -------------------------------------------------------------------------

    @api.model
    def _post_payload(self, export_type, payload):
        params = self.env["ir.config_parameter"].sudo()
        url = params.get_param("hubspot_export.webhook_url")
        login = params.get_param("hubspot_export.basic_auth_login")
        password = params.get_param("hubspot_export.basic_auth_password")

        if not url:
            raise UserError(_("L'URL du webhook n'est pas configurée."))
        if not login or not password:
            raise UserError(_("L'identifiant ou le mot de passe Basic Auth n'est pas configuré."))

        record_count = self._count_payload_records(payload)

        try:
            response = requests.post(
                url,
                auth=(login, password),
                json=payload,
                timeout=60,
                headers={"Content-Type": "application/json"},
            )
            success = 200 <= response.status_code < 300

            self._create_log(
                export_type=export_type,
                status="success" if success else "error",
                record_count=record_count,
                response_code=response.status_code,
                message=response.text[:2000],
                payload=payload,
            )

            if not success:
                raise UserError(_("Erreur webhook %s : %s") % (response.status_code, response.text[:500]))

            return True

        except requests.RequestException as exc:
            self._create_log(
                export_type=export_type,
                status="error",
                record_count=record_count,
                response_code=0,
                message=str(exc),
                payload=payload,
            )
            _logger.exception("Erreur lors de l'export HubSpot")
            raise UserError(_("Erreur lors de l'appel au webhook : %s") % exc)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @api.model
    def _count_payload_records(self, payload):
        if isinstance(payload, dict):
            if "data" in payload:
                return len(payload.get("data") or [])
            if "entreprise" in payload:
                return len(payload.get("entreprise") or [])
        return len(payload) if isinstance(payload, list) else 0

    @api.model
    def _create_log(self, export_type, status, record_count, response_code, message, payload):
        preview = json.dumps(payload, ensure_ascii=False, indent=2, default=str)[:10000]
        self.env["hubspot.export.log"].sudo().create({
            "name": "%s - %s" % (fields.Datetime.now(), export_type),
            "export_type": export_type,
            "status": status,
            "record_count": record_count,
            "response_code": response_code,
            "message": message,
            "payload_preview": preview,
        })

    @api.model
    def _safe_get(self, record, field_name):
        if field_name in record._fields:
            value = record[field_name]
            if hasattr(value, "display_name"):
                return value.display_name or ""
            return value or ""
        return ""

    @api.model
    def _get_siret(self, partner):
        return (
            # company_registry en tete : c'est la ou vit le SIRET depuis
            # la v19. Les deux suivants restent pour les bases anterieures.
            self._safe_get(partner.commercial_partner_id, "company_registry")
            or self._safe_get(partner, "siret")
            or self._safe_get(partner, "x_studio_siret")
            or ""
        )

    @api.model
    def _get_siren(self, partner):
        siren = self._safe_get(partner, "x_studio_siren")
        if siren:
            return siren
        siret = self._get_siret(partner)
        return siret[:9] if siret and len(siret) >= 9 else ""

    @api.model
    def _export_only_updated(self):
        value = self.env["ir.config_parameter"].sudo().get_param("hubspot_export.only_updated", "False")
        return str(value).lower() in ("true", "1", "yes")
