# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    iziqo_api_url = fields.Char(
        string="URL de la collection clients Iziqo",
        config_parameter="iziqo_sync.api_url",
        help="Laisser vide désactive complètement la synchronisation.",
    )
    iziqo_auth_type = fields.Selection(
        [
            ("none", "Aucune"),
            ("bearer", "Token Bearer"),
            ("apikey", "Clé d'API dans un en-tête"),
            ("basic", "Basic Auth"),
        ],
        string="Authentification",
        config_parameter="iziqo_sync.auth_type",
        default="bearer",
    )
    iziqo_api_key = fields.Char(
        string="Token / clé d'API",
        config_parameter="iziqo_sync.api_key",
    )
    iziqo_api_key_header = fields.Char(
        string="Nom de l'en-tête",
        config_parameter="iziqo_sync.api_key_header",
        default="X-API-Key",
    )
    iziqo_login = fields.Char(
        string="Identifiant Basic Auth",
        config_parameter="iziqo_sync.login",
    )
    iziqo_password = fields.Char(
        string="Mot de passe Basic Auth",
        config_parameter="iziqo_sync.password",
    )
    iziqo_identifier_field = fields.Selection(
        [
            ("siret", "SIRET"),
            ("ref", "Code client (ref)"),
            ("id", "ID Odoo"),
        ],
        string="Identifiant de la ressource",
        config_parameter="iziqo_sync.identifier_field",
        default="siret",
        help="Valeur utilisée dans l'URL du PATCH : PATCH {url}/{identifiant}. "
        "Repli sur le SIRET puis sur l'ID Odoo si la valeur est vide.",
    )
    iziqo_scope = fields.Selection(
        [
            ("customers_and_prospects", "Sociétés clientes et prospects"),
            ("customers", "Sociétés clientes uniquement (vente déjà passée)"),
            ("flagged", "Sociétés cochées « Iziqo » uniquement"),
        ],
        string="Périmètre",
        config_parameter="iziqo_sync.scope",
        default="customers_and_prospects",
    )
    iziqo_realtime = fields.Boolean(
        string="Envoi immédiat après enregistrement",
        config_parameter="iziqo_sync.realtime",
        default=True,
        help="Décoché, les fiches sont mises en file et envoyées par le cron.",
    )
    iziqo_timeout = fields.Integer(
        string="Timeout HTTP (secondes)",
        config_parameter="iziqo_sync.timeout",
        default=15,
    )
    iziqo_max_attempts = fields.Integer(
        string="Nombre maximum de tentatives",
        config_parameter="iziqo_sync.max_attempts",
        default=5,
    )
    iziqo_keep_days = fields.Integer(
        string="Conservation du journal (jours)",
        config_parameter="iziqo_sync.keep_days",
        default=30,
        help="Les envois réussis plus anciens sont purgés par le cron de purge.",
    )

    # -------------------------------------------------------------------------
    # Boutons
    # -------------------------------------------------------------------------

    def action_iziqo_test_connection(self):
        """Vérifie l'accès à la collection par un GET.

        Volontairement en lecture seule : un POST de test créerait un client
        factice dans la base Iziqo.
        """
        self.ensure_one()
        connector = self.env["iziqo.connector"]
        params = connector._iziqo_params()
        if not params["url"]:
            raise UserError(_("Renseignez d'abord l'URL de la collection clients Iziqo."))

        success, status_code, message = connector._iziqo_request(
            "GET", params["url"].rstrip("/"), None, params
        )
        if not success:
            raise UserError(
                _(
                    "GET %(url)s a répondu %(code)s : %(body)s\n\n"
                    "401 / 403 : authentification à revoir. "
                    "404 : URL de collection inexacte. "
                    "0 : Iziqo injoignable depuis ce serveur."
                )
                % {
                    "url": params["url"].rstrip("/"),
                    "code": status_code,
                    "body": message[:500],
                }
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": _("Accès à l'API Iziqo OK (GET, code %s).") % status_code,
                "sticky": False,
            },
        }

    def action_iziqo_sync_all(self):
        self.ensure_one()
        result = self.env["res.partner"].action_iziqo_sync_all()
        message = _("%s fiche(s) mise(s) en file d'attente.") % result["queued"]
        if result["missing_siret"]:
            message += _(
                " %s société(s) écartée(s) faute de SIRET."
            ) % result["missing_siret"]
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": message,
                "sticky": bool(result["missing_siret"]),
            },
        }
