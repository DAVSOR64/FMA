# -*- coding: utf-8 -*-
"""Couche transport HTTP vers l'API REST Iziqo.

Toute la configuration passe par ir.config_parameter (voir res_config_settings)
afin de rester modifiable en production sans redeploiement.
"""
import logging

import requests

from odoo import api, models

_logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15
DEFAULT_MAX_ATTEMPTS = 5
# Attente avant la prochaine tentative, en minutes, indexee par n° de tentative.
RETRY_DELAYS = {1: 5, 2: 15, 3: 60, 4: 240, 5: 1440}


class IziqoConnector(models.AbstractModel):
    _name = "iziqo.connector"
    _description = "Connecteur HTTP Iziqo"

    # -------------------------------------------------------------------------
    # Configuration
    # -------------------------------------------------------------------------

    @api.model
    def _iziqo_params(self):
        get_param = self.env["ir.config_parameter"].sudo().get_param
        return {
            "url": (get_param("iziqo_sync.api_url") or "").strip(),
            "auth_type": get_param("iziqo_sync.auth_type") or "bearer",
            "api_key": (get_param("iziqo_sync.api_key") or "").strip(),
            "api_key_header": (get_param("iziqo_sync.api_key_header") or "X-API-Key").strip(),
            "login": (get_param("iziqo_sync.login") or "").strip(),
            "password": get_param("iziqo_sync.password") or "",
            "identifier_field": get_param("iziqo_sync.identifier_field") or "ref",
            "scope": get_param("iziqo_sync.scope") or "customers_and_prospects",
            "timeout": self._iziqo_int(get_param("iziqo_sync.timeout"), DEFAULT_TIMEOUT),
            "max_attempts": self._iziqo_int(
                get_param("iziqo_sync.max_attempts"), DEFAULT_MAX_ATTEMPTS
            ),
            "realtime": self._iziqo_bool(get_param("iziqo_sync.realtime"), True),
        }

    @api.model
    def _iziqo_is_configured(self):
        return bool(self._iziqo_params()["url"])

    @api.model
    def _iziqo_int(self, value, default):
        try:
            result = int(value)
        except (TypeError, ValueError):
            return default
        return result if result > 0 else default

    @api.model
    def _iziqo_bool(self, value, default):
        if value is None or value == "":
            return default
        return str(value).lower() in ("true", "1", "yes", "oui")

    # -------------------------------------------------------------------------
    # Appel HTTP
    # -------------------------------------------------------------------------

    @api.model
    def _iziqo_headers(self, params):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        auth_type = params["auth_type"]
        if auth_type == "bearer" and params["api_key"]:
            headers["Authorization"] = "Bearer %s" % params["api_key"]
        elif auth_type == "apikey" and params["api_key"]:
            headers[params["api_key_header"] or "X-API-Key"] = params["api_key"]
        return headers

    @api.model
    def _iziqo_request(self, method, url, payload, params):
        """Appelle Iziqo et renvoie (succes, code HTTP, message).

        `payload` a None : requete sans corps (test d'acces en GET).

        Ne leve jamais : les erreurs reseau sont renvoyees avec un code 0 pour
        que l'appelant puisse programmer une relance.
        """
        auth = None
        if params["auth_type"] == "basic" and params["login"]:
            auth = (params["login"], params["password"])

        try:
            response = requests.request(
                method,
                url,
                json=payload,
                auth=auth,
                headers=self._iziqo_headers(params),
                timeout=params["timeout"],
            )
        except requests.RequestException as exc:
            _logger.warning("Iziqo: echec de l'appel %s %s : %s", method, url, exc)
            return False, 0, str(exc)

        success = 200 <= response.status_code < 300
        message = (response.text or "")[:4000]
        if not success:
            _logger.warning(
                "Iziqo: reponse %s pour %s %s : %s",
                response.status_code,
                method,
                url,
                message[:500],
            )
        return success, response.status_code, message
