# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # --- Connexion (commune aux deux collections) ----------------------------
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

    # --- Collection clients --------------------------------------------------
    iziqo_api_url = fields.Char(
        string="URL de la collection clients",
        config_parameter="iziqo_sync.api_url",
        help="Laisser vide désactive la synchronisation des clients.",
    )
    iziqo_identifier_field = fields.Selection(
        [
            ("id", "ID Odoo"),
            ("siret", "SIRET"),
            ("ref", "Code client (ref)"),
        ],
        string="Identifiant de la ressource",
        config_parameter="iziqo_sync.identifier_field",
        default="id",
        help="Valeur utilisée dans l'URL du PATCH : PATCH {url}/{identifiant}. "
        "Repli sur l'ID Odoo si la valeur est vide.",
    )
    iziqo_scope = fields.Selection(
        [
            ("customers_and_prospects", "Sociétés clientes et prospects"),
            ("customers", "Sociétés clientes uniquement (vente déjà passée)"),
            ("flagged", "Sociétés cochées « Iziqo » uniquement"),
        ],
        string="Périmètre clients",
        config_parameter="iziqo_sync.scope",
        default="customers_and_prospects",
    )

    # --- Collection commerciaux ---------------------------------------------
    iziqo_employee_api_url = fields.Char(
        string="URL de la collection commerciaux",
        config_parameter="iziqo_sync.employee_api_url",
        help="Laisser vide désactive la synchronisation des commerciaux.",
    )
    # Pas d'identifiant configurable ici, a la difference des clients : Iziqo
    # refuse en 400 tout PATCH dont l'identifiant d'URL differe du « odoo_id »
    # du payload. C'est aussi la valeur envoyee dans « id_employe_commercial »
    # du payload client, donc la cle de jointure entre les deux collections.
    iziqo_employee_scope = fields.Selection(
        [
            ("department", "Employés du département commercial"),
            ("all", "Tous les employés"),
        ],
        string="Périmètre commerciaux",
        config_parameter="iziqo_sync.employee_scope",
        default="department",
    )
    iziqo_employee_department = fields.Char(
        string="Département commercial",
        config_parameter="iziqo_sync.employee_department",
        default="Commerce",
        help="Nom exact du département, et non son identifiant : il diffère "
        "d'un environnement à l'autre.",
    )

    # --- Comportement --------------------------------------------------------
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
        """Vérifie l'accès aux collections configurées, par un GET.

        Volontairement en lecture seule : un POST de test créerait une fiche
        factice dans la base Iziqo. Toutes les collections n'exposent pas de
        GET -- celle des commerciaux n'en a pas -- et un GET dessus répondrait
        404 alors que la configuration est bonne : celles-là sont seulement
        signalées comme non testables.
        """
        self.ensure_one()
        connector = self.env["iziqo.connector"]
        params = connector._iziqo_params()
        resources = [
            (label, url, supports_get)
            for _model, label, url, supports_get in connector._iziqo_resources()
            if url
        ]
        if not resources:
            raise UserError(
                _("Renseignez d'abord au moins une URL de collection Iziqo.")
            )

        successes = []
        failures = []
        untested = []
        for label, url, supports_get in resources:
            if not supports_get:
                untested.append(label)
                continue
            success, status_code, message = connector._iziqo_request(
                "GET", url.rstrip("/"), None, params
            )
            if success:
                successes.append(_("%(label)s : OK (code %(code)s)") % {
                    "label": label, "code": status_code,
                })
            else:
                failures.append(_("%(label)s : code %(code)s sur %(url)s — %(body)s") % {
                    "label": label,
                    "code": status_code,
                    "url": url.rstrip("/"),
                    "body": message[:300],
                })

        if failures:
            raise UserError(
                "\n\n".join(failures)
                + _(
                    "\n\n401 / 403 : authentification à revoir. "
                    "404 : URL de collection inexacte. "
                    "0 : Iziqo injoignable depuis ce serveur."
                )
            )
        if untested:
            successes.append(
                _("%s : URL renseignée, collection non interrogeable en lecture")
                % " et ".join(untested)
            )
        return self._iziqo_notification(" · ".join(successes))

    def action_iziqo_sync_all(self):
        """Met tous les clients du périmètre en file d'attente."""
        self.ensure_one()
        result = self.env["res.partner"].action_iziqo_sync_all()
        message = _("%s client(s) mis en file d'attente.") % result["queued"]
        if result["missing_siret"]:
            message += _(" %s société(s) écartée(s) faute de SIRET.") % result[
                "missing_siret"
            ]
        return self._iziqo_notification(message, sticky=bool(result["missing_siret"]))

    def action_iziqo_sync_all_employees(self):
        """Met tous les commerciaux du périmètre en file d'attente."""
        self.ensure_one()
        result = self.env["hr.employee"].action_iziqo_sync_all_employees()
        message = _("%s commercial/commerciaux mis en file d'attente.") % result["queued"]
        if result["missing_email"]:
            message += _(
                " %s écarté(s) faute d'e-mail professionnel."
            ) % result["missing_email"]
        return self._iziqo_notification(message, sticky=bool(result["missing_email"]))

    def _iziqo_notification(self, message, sticky=False):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": message,
                "sticky": sticky,
            },
        }
