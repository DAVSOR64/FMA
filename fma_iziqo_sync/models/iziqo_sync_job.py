# -*- coding: utf-8 -*-
"""File d'attente des envois vers Iziqo, toutes ressources confondues.

Un job = une fiche a pousser, designee par (res_model, res_id). Il sert a la
fois de tampon -- l'envoi a lieu apres le commit, donc en dehors de la
transaction de l'utilisateur -- et de journal : on garde le payload envoye, le
code HTTP et le message de reponse.
"""
import json
import logging

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models

from .iziqo_connector import RETRY_DELAYS

_logger = logging.getLogger(__name__)

# Nombre de jobs traites par passage de cron.
CRON_BATCH_SIZE = 100
# Nombre d'echecs reseau consecutifs avant d'interrompre le lot en cours.
TRANSPORT_ERROR_LIMIT = 5
# Duree de conservation par defaut des envois reussis, en jours.
DEFAULT_KEEP_DAYS = 30


class IziqoSyncJob(models.Model):
    _name = "iziqo.sync.job"
    _description = "Synchronisation Iziqo"
    _order = "id desc"
    _rec_name = "record_name"

    res_model = fields.Selection(
        selection="_selection_res_model",
        string="Ressource",
        required=True,
        index=True,
    )
    res_id = fields.Integer(string="ID Odoo", required=True, index=True)
    record_name = fields.Char(
        string="Fiche",
        compute="_compute_record_name",
        compute_sudo=True,
        store=True,
        readonly=True,
        help="Nom de la fiche au moment de la mise en file. Stocké pour rester "
        "consultable même après renommage ou suppression.",
    )
    operation = fields.Selection(
        [("create", "Création"), ("update", "Modification")],
        string="Opération",
        required=True,
        default="update",
    )
    state = fields.Selection(
        [
            ("pending", "À envoyer"),
            ("done", "Envoyé"),
            ("error", "En échec"),
            ("cancelled", "Annulé"),
        ],
        string="État",
        required=True,
        default="pending",
        index=True,
    )
    origin = fields.Selection(
        [
            ("auto", "Automatique"),
            ("manual", "Manuel"),
            ("full", "Synchronisation complète"),
        ],
        string="Origine",
        default="auto",
    )
    attempt_count = fields.Integer(string="Tentatives", default=0, readonly=True)
    last_attempt_date = fields.Datetime(string="Dernière tentative", readonly=True)
    next_attempt_date = fields.Datetime(string="Prochaine tentative", index=True)
    http_method = fields.Char(string="Méthode HTTP", readonly=True)
    endpoint = fields.Char(string="Endpoint", readonly=True)
    response_code = fields.Integer(string="Code réponse", readonly=True)
    response_message = fields.Text(string="Réponse", readonly=True)
    error_message = fields.Text(string="Erreur", readonly=True)
    payload = fields.Text(string="Payload envoyé", readonly=True)

    @api.model
    def _selection_res_model(self):
        """Ressources synchronisables. Point d'entree pour en ajouter une."""
        return [
            ("res.partner", "Client"),
            ("hr.employee", "Commercial"),
        ]

    @api.depends("res_model", "res_id")
    def _compute_record_name(self):
        for job in self:
            record = job._iziqo_record()
            job.record_name = (
                record.display_name if record else "%s,%s" % (job.res_model, job.res_id)
            )

    def _iziqo_record(self):
        """La fiche visee, ou un recordset vide si elle n'existe plus."""
        self.ensure_one()
        if not self.res_model or self.res_model not in self.env:
            return self.env["iziqo.sync.job"].browse()
        return self.env[self.res_model].sudo().browse(self.res_id).exists()

    # -------------------------------------------------------------------------
    # Traitement
    # -------------------------------------------------------------------------

    def _process(self):
        """Envoie les jobs du recordset. Ne leve jamais d'exception."""
        connector = self.env["iziqo.connector"]
        params = connector._iziqo_params()

        transport_errors = 0
        for job in self._iziqo_lock():
            try:
                with self.env.cr.savepoint():
                    _success, status_code = job._process_one(params, connector)
            except Exception:  # noqa: BLE001 - le job sera relance par le cron
                _logger.exception("Iziqo: échec du traitement du job %s", job.id)
                continue

            # Coupe-circuit : inutile d'attendre le timeout sur chaque job si
            # Iziqo est injoignable, les jobs restants seront relances plus tard.
            transport_errors = transport_errors + 1 if status_code == 0 else 0
            if transport_errors >= TRANSPORT_ERROR_LIMIT:
                _logger.warning(
                    "Iziqo: %s échecs réseau consécutifs, arrêt du lot.",
                    transport_errors,
                )
                break
        return True

    def _iziqo_lock(self):
        """Verrouille les jobs encore a envoyer pour eviter qu'un envoi
        post-commit et le cron ne traitent le meme job en parallele."""
        if not self:
            return self
        self.env.flush_all()
        self.env.cr.execute(
            """
            SELECT id FROM iziqo_sync_job
             WHERE id IN %s AND state = 'pending'
             ORDER BY id
               FOR UPDATE SKIP LOCKED
            """,
            (tuple(self.ids),),
        )
        return self.browse([row[0] for row in self.env.cr.fetchall()])

    def _process_one(self, params, connector):
        self.ensure_one()
        record = self._iziqo_record()
        if not record:
            self.write({
                "state": "cancelled",
                "error_message": _("La fiche a été supprimée avant l'envoi."),
                "next_attempt_date": False,
            })
            # None : aucune tentative reseau, ne compte pas dans le coupe-circuit.
            return False, None

        if not record._iziqo_is_configured():
            _logger.info(
                "Iziqo: URL non configurée pour %s, job %s laissé en attente.",
                self.res_model,
                self.id,
            )
            return False, None

        payload = record._iziqo_payload(self.operation)
        method, url = self._iziqo_endpoint(record)
        success, status_code, message = connector._iziqo_request(
            method, url, payload, params
        )

        # POST refuse en 409 : Iziqo connait deja cette fiche (cas classique du
        # chargement initial des historiques). On bascule en PATCH.
        if not success and status_code == 409 and self.operation == "create":
            _logger.info(
                "Iziqo: %s déjà présent (409), bascule en mise à jour.",
                record.display_name,
            )
            self.operation = "update"
            payload = record._iziqo_payload(self.operation)
            method, url = self._iziqo_endpoint(record)
            success, status_code, message = connector._iziqo_request(
                method, url, payload, params
            )

        attempt_count = self.attempt_count + 1
        vals = {
            "attempt_count": attempt_count,
            "last_attempt_date": fields.Datetime.now(),
            "http_method": method,
            "endpoint": url,
            "response_code": status_code,
            "response_message": message,
            "payload": json.dumps(payload, ensure_ascii=False, indent=2, default=str)[:20000],
        }

        if success:
            vals.update({
                "state": "done",
                "error_message": False,
                "next_attempt_date": False,
            })
        else:
            error = message or _("Erreur inconnue")
            if attempt_count >= params["max_attempts"]:
                vals.update({
                    "state": "error",
                    "error_message": _("Abandon après %(count)s tentative(s) : %(error)s")
                    % {"count": attempt_count, "error": error},
                    "next_attempt_date": False,
                })
            else:
                delay = RETRY_DELAYS.get(attempt_count, 1440)
                vals.update({
                    "state": "pending",
                    "error_message": error,
                    "next_attempt_date": fields.Datetime.now()
                    + relativedelta(minutes=delay),
                })

        self.write(vals)
        record._iziqo_store_result(success, vals.get("error_message") or False)
        return success, status_code

    def _iziqo_endpoint(self, record):
        """(methode, url) du contrat REST Iziqo :

        - creation     : POST sur la collection ;
        - modification : PATCH sur la ressource identifiee.
        """
        self.ensure_one()
        url = (record._iziqo_url() or "").rstrip("/")
        if self.operation == "update":
            return "PATCH", "%s/%s" % (url, record._iziqo_identifier())
        return "POST", url

    # -------------------------------------------------------------------------
    # Boutons
    # -------------------------------------------------------------------------

    def action_retry(self):
        self.write({
            "state": "pending",
            "attempt_count": 0,
            "next_attempt_date": False,
            "error_message": False,
        })
        self._process()
        return True

    def action_cancel(self):
        self.filtered(lambda job: job.state == "pending").write({
            "state": "cancelled",
            "next_attempt_date": False,
        })
        return True

    def action_open_record(self):
        """Ouvre la fiche visee par le job."""
        self.ensure_one()
        record = self._iziqo_record()
        if not record:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": self.res_model,
            "res_id": self.res_id,
            "view_mode": "form",
            "views": [(False, "form")],
        }

    # -------------------------------------------------------------------------
    # Cron
    # -------------------------------------------------------------------------

    @api.model
    def _cron_flush(self, limit=CRON_BATCH_SIZE):
        """Rattrapage : envoie les jobs en attente dont l'heure est venue."""
        jobs = self.sudo().search(self._cron_domain(), limit=limit, order="id asc")
        if not jobs:
            return True
        _logger.info("Iziqo: traitement de %s job(s) en attente.", len(jobs))
        return jobs._process()

    @api.model
    def _cron_domain(self):
        return [
            ("state", "=", "pending"),
            "|",
            ("next_attempt_date", "=", False),
            ("next_attempt_date", "<=", fields.Datetime.now()),
        ]

    @api.model
    def _cron_vacuum(self):
        """Purge les envois reussis au-dela de la duree de conservation."""
        keep_days = self.env["iziqo.connector"]._iziqo_int(
            self.env["ir.config_parameter"].sudo().get_param("iziqo_sync.keep_days"),
            DEFAULT_KEEP_DAYS,
        )
        limit_date = fields.Datetime.now() - relativedelta(days=keep_days)
        jobs = self.sudo().search([
            ("state", "=", "done"),
            ("create_date", "<", limit_date),
        ])
        if jobs:
            _logger.info(
                "Iziqo: purge de %s envoi(s) de plus de %s jours.", len(jobs), keep_days
            )
            jobs.unlink()
        return True
