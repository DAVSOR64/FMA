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
    def _prepare_entreprises_payload(self, force_full=False):
        partners = self._get_partners_to_export(force_full=force_full)
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

        return {"entreprise": entreprises}

    @api.model
    def _get_partners_to_export(self, force_full=False):
        # Sociétés et prospects/clients. On évite les contacts enfants purs pour limiter les doublons.
        domain = [
            ("active", "=", True),
            "|", ("is_company", "=", True), ("parent_id", "=", False),
            "|", ("customer_rank", ">", 0), ("supplier_rank", "=", 0),
        ]
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

        return {"data": data}

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
        return self._safe_get(partner, "siret") or self._safe_get(partner, "x_studio_siret") or ""

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
