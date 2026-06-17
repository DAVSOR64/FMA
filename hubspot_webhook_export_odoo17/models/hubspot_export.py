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
        [("clients", "Clients"), ("quotes", "Chiffrages / Devis")],
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
    def action_export_clients(self):
        payload = self._prepare_clients_payload()
        return self._post_payload("clients", payload)

    @api.model
    def action_export_quotes(self):
        payload = self._prepare_quotes_payload()
        return self._post_payload("quotes", payload)

    @api.model
    def cron_export_clients_and_quotes(self):
        self.action_export_clients()
        self.action_export_quotes()

    # -------------------------------------------------------------------------
    # Payload clients
    # -------------------------------------------------------------------------

    @api.model
    def _prepare_clients_payload(self):
        partners = self._get_partners_to_export()
        payload = []

        SaleOrder = self.env["sale.order"].sudo()

        for partner in partners:
            commercial_orders = SaleOrder.search_count([
                ("partner_id", "child_of", partner.id),
                ("state", "in", ["sale", "done"]),
            ])
            quotations = SaleOrder.search_count([
                ("partner_id", "child_of", partner.id),
                ("state", "in", ["draft", "sent"]),
            ])

            created_by = partner.create_uid.name if partner.create_uid else ""
            tags = ", ".join(partner.category_id.mapped("name"))

            payload.append({
                "Civilité": partner.title.name or "",
                "Code Diap": self._safe_get(partner, "x_studio_code_diap"),
                "Code Tiers": partner.ref or "",
                "Compte": self._get_receivable_account_code(partner),
                "Créé le": fields.Date.to_string(partner.create_date.date()) if partner.create_date else "",
                "Créé par": created_by,
                "E-mail": partner.email or "",
                "Nom complet": partner.name or "",
                "Pays": partner.country_id.name or "",
                "SIRET": self._safe_get(partner, "siret") or self._safe_get(partner, "x_studio_siret"),
                "Téléphone": partner.phone or partner.mobile or "",
                "Ville": partner.city or "",
                "SIREN": self._safe_get(partner, "x_studio_siren"),
                "Code postal": partner.zip or "",
                "Étiquettes": tags,
                "Nombre de bons de commande": commercial_orders,
                "Nombre de commandes clients": commercial_orders,
                "Nom Com": partner.commercial_company_name or "",
                "Nom": partner.name or "",
                "Nom d'affichage": partner.display_name or "",
                "Rue": partner.street or "",
                "Rue 2": partner.street2 or "",
            })

        return payload

    @api.model
    def _get_partners_to_export(self):
        domain = [("customer_rank", ">", 0), ("active", "=", True)]
        if self._export_only_updated():
            since = fields.Datetime.now() - timedelta(days=1)
            domain.append(("write_date", ">=", since))
        return self.env["res.partner"].sudo().search(domain)

    # -------------------------------------------------------------------------
    # Payload devis / chiffrages
    # -------------------------------------------------------------------------

    @api.model
    def _prepare_quotes_payload(self):
        orders = self._get_sale_orders_to_export()
        data = []

        for order in orders:
            partner = order.partner_id
            date_creation = order.create_date.date() if order.create_date else False
            date_envoi = self._get_quotation_sent_date(order)

            data.append({
                "Devis": order.name or "",
                "Client": partner.ref or str(partner.id),
                "Activite": self._get_order_activity(order),
                "Prix": order.amount_total,
                "Date_Creation": fields.Date.to_string(date_creation) if date_creation else "",
                "Date_Envoi": fields.Date.to_string(date_envoi) if date_envoi else "",
                "Message": "",
                "Chantier": self._get_site_name(order),
                "SIREN": self._safe_get(partner, "x_studio_siren"),
                "SIRET": self._safe_get(partner, "siret") or self._safe_get(partner, "x_studio_siret"),
                "Proprietaire": order.user_id.name or "",
                "Commande": order.name if order.state in ["sale", "done"] else "",
                "statut_chiffrage": self._map_order_status(order),
            })

        return {"data": data}

    @api.model
    def _get_sale_orders_to_export(self):
        domain = [("state", "in", ["draft", "sent", "sale", "done", "cancel"])]
        if self._export_only_updated():
            since = fields.Datetime.now() - timedelta(days=1)
            domain.append(("write_date", ">=", since))
        return self.env["sale.order"].sudo().search(domain)

    @api.model
    def _get_quotation_sent_date(self, order):
        # Odoo ne stocke pas toujours une date d'envoi standard.
        # On prend la première date d'un message sortant si disponible.
        message = self.env["mail.message"].sudo().search([
            ("model", "=", "sale.order"),
            ("res_id", "=", order.id),
            ("message_type", "=", "email"),
        ], order="date asc", limit=1)
        return message.date.date() if message and message.date else False

    @api.model
    def _get_order_activity(self, order):
        # À adapter si vous avez un champ Studio activité/récap du devis.
        return self._safe_get(order, "x_studio_activite") or order.note or ""

    @api.model
    def _get_site_name(self, order):
        # À adapter selon le champ chantier réellement utilisé.
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
        batch_size = self._get_batch_size()

        if not url:
            raise UserError(_("L'URL du webhook n'est pas configurée."))
        if not login or not password:
            raise UserError(_("L'identifiant ou le mot de passe Basic Auth n'est pas configuré."))

        records = self._extract_payload_records(payload)
        total_count = len(records)

        if not total_count:
            self._create_log(
                export_type=export_type,
                status="success",
                record_count=0,
                response_code=0,
                message=_("Aucune donnée à exporter."),
                payload=payload,
            )
            return True

        for batch_number, batch_records in enumerate(self._chunk_records(records, batch_size), start=1):
            batch_payload = self._build_batch_payload(payload, batch_records)
            batch_count = len(batch_records)
            message_prefix = _("Lot %(batch_number)s - %(batch_count)s/%(total_count)s enregistrements") % {
                "batch_number": batch_number,
                "batch_count": batch_count,
                "total_count": total_count,
            }

            try:
                response = requests.post(
                    url,
                    auth=(login, password),
                    json=batch_payload,
                    timeout=60,
                    headers={"Content-Type": "application/json"},
                )
                success = 200 <= response.status_code < 300

                self._create_log(
                    export_type=export_type,
                    status="success" if success else "error",
                    record_count=batch_count,
                    response_code=response.status_code,
                    message="%s\n%s" % (message_prefix, response.text[:2000]),
                    payload=batch_payload,
                )

                if not success:
                    raise UserError(
                        _("Erreur webhook %(code)s sur %(prefix)s : %(message)s") % {
                            "code": response.status_code,
                            "prefix": message_prefix,
                            "message": response.text[:500],
                        }
                    )

            except requests.RequestException as exc:
                self._create_log(
                    export_type=export_type,
                    status="error",
                    record_count=batch_count,
                    response_code=0,
                    message="%s\n%s" % (message_prefix, str(exc)),
                    payload=batch_payload,
                )
                _logger.exception("Erreur lors de l'export HubSpot")
                raise UserError(_("Erreur lors de l'appel au webhook : %s") % exc)

        return True

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @api.model
    def _get_batch_size(self):
        value = self.env["ir.config_parameter"].sudo().get_param("hubspot_export.batch_size", "100")
        try:
            batch_size = int(value)
        except (TypeError, ValueError):
            batch_size = 100
        return max(batch_size, 1)

    @api.model
    def _extract_payload_records(self, payload):
        if isinstance(payload, dict):
            return payload.get("data", []) or []
        return payload or []

    @api.model
    def _build_batch_payload(self, original_payload, batch_records):
        if isinstance(original_payload, dict):
            batch_payload = dict(original_payload)
            batch_payload["data"] = batch_records
            return batch_payload
        return batch_records

    @api.model
    def _chunk_records(self, records, batch_size):
        for index in range(0, len(records), batch_size):
            yield records[index:index + batch_size]

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
    def _get_receivable_account_code(self, partner):
        prop = partner.property_account_receivable_id
        return prop.code if prop else ""

    @api.model
    def _export_only_updated(self):
        value = self.env["ir.config_parameter"].sudo().get_param("hubspot_export.only_updated", "False")
        return str(value).lower() in ("true", "1", "yes")
