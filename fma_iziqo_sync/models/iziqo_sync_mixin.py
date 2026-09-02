# -*- coding: utf-8 -*-
"""Mecanique commune a toutes les ressources synchronisees vers Iziqo.

Un modele devient synchronisable en heritant de ce mixin et en fournissant :
son perimetre (_iziqo_is_eligible), son payload (_iziqo_payload), ses
identifiants possibles (_iziqo_identifier_candidates) et les cles de
parametres qui portent son URL et son identifiant.

Le mixin apporte le reste : declenchement sur create/write, mise en file,
envoi post-commit, trace du dernier envoi et bouton de synchronisation
manuelle.
"""
import logging
from urllib.parse import quote

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Au-dela de ce nombre de fiches touchees dans une meme transaction (import,
# action de masse, migration), on laisse le cron faire les envois.
REALTIME_MAX_JOBS = 20


class IziqoSyncMixin(models.AbstractModel):
    _name = "iziqo.sync.mixin"
    _description = "Synchronisation Iziqo"

    # --- A definir par le modele concret -------------------------------------
    # Champs dont la modification justifie un renvoi.
    _iziqo_tracked_fields = frozenset()
    # Cles ir.config_parameter portant l'URL de collection et l'identifiant.
    _iziqo_url_param = None
    _iziqo_identifier_param = None
    _iziqo_default_identifier = "id"

    iziqo_sync_excluded = fields.Boolean(
        string="Exclure de la synchro Iziqo",
        copy=False,
        help="Coché, la fiche n'est plus poussée automatiquement vers Iziqo.",
    )
    iziqo_last_sync_date = fields.Datetime(
        string="Dernière synchro Iziqo", readonly=True, copy=False
    )
    iziqo_last_sync_status = fields.Selection(
        [("success", "Succès"), ("error", "Erreur")],
        string="Statut dernière synchro",
        readonly=True,
        copy=False,
    )
    iziqo_last_sync_error = fields.Text(
        string="Dernière erreur Iziqo", readonly=True, copy=False
    )

    # -------------------------------------------------------------------------
    # Configuration
    # -------------------------------------------------------------------------

    @api.model
    def _iziqo_url(self):
        if not self._iziqo_url_param:
            return ""
        param = self.env["ir.config_parameter"].sudo().get_param(self._iziqo_url_param)
        return (param or "").strip()

    @api.model
    def _iziqo_is_configured(self):
        return bool(self._iziqo_url())

    @api.model
    def _iziqo_identifier_field(self):
        param = False
        if self._iziqo_identifier_param:
            param = self.env["ir.config_parameter"].sudo().get_param(
                self._iziqo_identifier_param
            )
        return param or self._iziqo_default_identifier

    # -------------------------------------------------------------------------
    # A surcharger
    # -------------------------------------------------------------------------

    def _iziqo_is_eligible(self):
        """La fiche entre-t-elle dans le perimetre automatique ?"""
        raise NotImplementedError

    def _iziqo_payload(self, operation="update"):
        """Corps JSON envoye a Iziqo."""
        raise NotImplementedError

    def _iziqo_identifier_candidates(self):
        """Valeurs utilisables comme identifiant de ressource, par cle de
        parametre. Toujours inclure "id"."""
        self.ensure_one()
        return {"id": str(self.id)}

    def _iziqo_manual_targets(self):
        """Fiches acceptees par le bouton manuel. Le perimetre automatique est
        ignore -- c'est tout l'interet du bouton -- mais pas les conditions
        techniques. Leve une UserError explicite s'il ne reste rien."""
        raise NotImplementedError

    def _iziqo_targets(self):
        """Fiches a pousser pour ce recordset."""
        return self.filtered(lambda record: record._iziqo_is_eligible())

    # -------------------------------------------------------------------------
    # Declenchement
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._iziqo_sync_after_change(default_operation="create")
        return records

    def write(self, vals):
        result = super().write(vals)
        if self._iziqo_tracked_fields.intersection(vals):
            self._iziqo_sync_after_change()
        return result

    def _iziqo_sync_after_change(self, default_operation=None):
        """Met en file les fiches concernees et programme l'envoi post-commit."""
        if self.env.context.get("iziqo_sync_skip") or self.env.context.get("install_mode"):
            return False
        if not self._iziqo_is_configured():
            return False

        targets = self._iziqo_targets()
        if not targets:
            return False

        job_ids = targets._iziqo_enqueue(operation=default_operation)
        return self._iziqo_schedule_flush(job_ids)

    def _iziqo_enqueue(self, operation=None, origin="auto"):
        """Cree (ou reutilise) un job par fiche et renvoie les ids."""
        Job = self.env["iziqo.sync.job"].sudo()
        job_ids = []
        for record in self:
            wanted = operation or ("update" if record.iziqo_last_sync_date else "create")
            if wanted == "create" and record.iziqo_last_sync_date:
                # Fiche deja connue d'Iziqo : c'est une mise a jour.
                wanted = "update"
            job = Job.search(
                [
                    ("res_model", "=", record._name),
                    ("res_id", "=", record.id),
                    ("state", "=", "pending"),
                ],
                order="id desc",
                limit=1,
            )
            if job:
                # Une creation non encore envoyee reste une creation.
                if wanted == "create" and job.operation == "update":
                    job.operation = "create"
                job_ids.append(job.id)
            else:
                job_ids.append(
                    Job.create({
                        "res_model": record._name,
                        "res_id": record.id,
                        "operation": wanted,
                        "origin": origin,
                    }).id
                )
        return job_ids

    def _iziqo_schedule_flush(self, job_ids):
        """Programme l'envoi apres le commit, dans un curseur dedie."""
        if not job_ids:
            return False
        if not self.env["iziqo.connector"]._iziqo_params()["realtime"]:
            return False
        if self.env.context.get("import_file") or len(job_ids) > REALTIME_MAX_JOBS:
            _logger.info(
                "Iziqo: %s fiche(s) mise(s) en file, envoi laissé au cron.",
                len(job_ids),
            )
            return False

        registry = self.env.registry
        job_ids = list(job_ids)

        def _flush():
            try:
                with registry.cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    jobs = env["iziqo.sync.job"].browse(job_ids).exists()
                    jobs = jobs.filtered(
                        lambda job: job.state == "pending"
                        and (
                            not job.next_attempt_date
                            or job.next_attempt_date <= fields.Datetime.now()
                        )
                    )
                    if jobs:
                        jobs._process()
            except Exception:  # noqa: BLE001 - le cron reprendra les jobs
                _logger.exception("Iziqo: échec de l'envoi post-commit %s", job_ids)

        self.env.cr.postcommit.add(_flush)
        return True

    def _iziqo_store_result(self, success, error_message):
        """Trace du dernier envoi sur la fiche, sans redeclencher de synchro."""
        for record in self:
            record.sudo().with_context(iziqo_sync_skip=True).write({
                "iziqo_last_sync_date": fields.Datetime.now(),
                "iziqo_last_sync_status": "success" if success else "error",
                "iziqo_last_sync_error": False if success else error_message,
            })

    # -------------------------------------------------------------------------
    # Identifiant de ressource
    # -------------------------------------------------------------------------

    def _iziqo_identifier(self):
        """Valeur placee dans l'URL du PATCH, avec repli sur l'ID Odoo."""
        self.ensure_one()
        wanted = self._iziqo_identifier_field()
        identifier = self._iziqo_identifier_candidates().get(wanted)
        if not identifier:
            identifier = str(self.id)
            _logger.warning(
                "Iziqo: %s n'a pas de valeur pour l'identifiant « %s », "
                "repli sur l'ID Odoo %s.",
                self.display_name,
                wanted,
                identifier,
            )
        return quote(str(identifier), safe="")

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_iziqo_sync_now(self):
        """Bouton de la fiche / action de liste : envoi immediat."""
        if not self._iziqo_is_configured():
            raise UserError(
                _("L'URL de l'API Iziqo n'est pas configurée (Paramètres > Iziqo).")
            )

        targets = self._iziqo_manual_targets()
        job_ids = targets._iziqo_enqueue(origin="manual")
        self.env["iziqo.sync.job"].sudo().browse(job_ids)._process()

        errors = targets.filtered(lambda r: r.iziqo_last_sync_status == "error")
        if errors:
            message = _("Échec de la synchronisation de %(failed)s fiche(s) sur %(total)s.") % {
                "failed": len(errors),
                "total": len(targets),
            }
        else:
            message = _("%s fiche(s) synchronisée(s) vers Iziqo.") % len(targets)
        ignored = len(self) - len(targets)
        if ignored > 0:
            message += _(" %s fiche(s) ignorée(s).") % ignored
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "danger" if errors else "success",
                "message": message,
                "sticky": bool(errors),
            },
        }

    @api.model
    def _iziqo_sync_all(self):
        """Met en file tout le perimetre. L'envoi est laisse au cron pour ne
        pas bloquer la session. Renvoie le nombre de fiches mises en file."""
        records = self.sudo().with_context(active_test=False).search(
            [("iziqo_sync_excluded", "=", False)]
        )
        targets = records._iziqo_targets()
        job_ids = targets._iziqo_enqueue(origin="full")
        _logger.info(
            "Iziqo: %s fiche(s) %s mise(s) en file pour synchronisation complète.",
            len(job_ids),
            self._name,
        )
        return len(job_ids)
