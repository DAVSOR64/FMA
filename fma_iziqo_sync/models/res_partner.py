# -*- coding: utf-8 -*-
"""Declenchement de la synchronisation Iziqo sur creation / modification.

L'envoi HTTP n'est jamais fait dans la transaction de l'utilisateur : on cree
un job (iziqo.sync.job) puis on programme son traitement en post-commit. Si
l'envoi echoue, le cron de rattrapage reprend le job.
"""
import logging

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Au-dela de ce nombre de fiches touchees dans une meme transaction (import,
# action de masse, migration), on laisse le cron faire les envois.
REALTIME_MAX_JOBS = 20

# Champs dont la modification justifie un renvoi vers Iziqo : ceux du payload
# plus ceux qui pilotent l'appartenance au perimetre.
IZIQO_TRACKED_FIELDS = {
    "active",
    "city",
    "country_id",
    "customer_rank",
    "email",
    "is_company",
    "iziqo_sync_excluded",
    "name",
    "parent_id",
    "phone",
    "ref",
    "company_registry",
    "siret",
    "state_id",
    "street",
    "street2",
    "supplier_rank",
    "type",
    "vat",
    "x_studio_commercial_1",
    "x_studio_iziqo_1",
    "x_studio_siret",
    "zip",
}


class ResPartner(models.Model):
    _inherit = "res.partner"

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
    # Surcharges
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        partners._iziqo_sync_after_change(default_operation="create")
        return partners

    def write(self, vals):
        result = super().write(vals)
        if IZIQO_TRACKED_FIELDS.intersection(vals):
            self._iziqo_sync_after_change()
        return result

    # -------------------------------------------------------------------------
    # Declenchement
    # -------------------------------------------------------------------------

    def _iziqo_sync_after_change(self, default_operation=None):
        """Met en file les fiches concernees et programme l'envoi post-commit."""
        if self.env.context.get("iziqo_sync_skip") or self.env.context.get("install_mode"):
            return False
        if not self.env["iziqo.connector"]._iziqo_is_configured():
            return False

        targets = self._iziqo_targets()
        if not targets:
            return False

        job_ids = targets._iziqo_enqueue(operation=default_operation)
        return self._iziqo_schedule_flush(job_ids)

    def _iziqo_targets(self):
        """Fiches a pousser : les fiches eligibles du recordset, et la societe
        parente quand c'est une adresse de livraison / de facturation qui bouge
        (elle alimente les colonnes "... livraison" du payload)."""
        targets = self.env["res.partner"]
        for partner in self:
            if partner._iziqo_is_eligible():
                targets |= partner
            elif partner.parent_id and partner.type in ("delivery", "invoice"):
                if partner.parent_id._iziqo_is_eligible():
                    targets |= partner.parent_id
        return targets

    def _iziqo_is_eligible(self):
        """Perimetre : societes avec SIRET, filtrees par iziqo_sync.scope.

        Le SIRET est la cle de rapprochement cote Iziqo : une fiche sans SIRET
        n'est jamais envoyee, elle le sera automatiquement des que le SIRET
        sera renseigne (le champ est suivi).
        """
        self.ensure_one()
        if self.iziqo_sync_excluded or not self.is_company:
            return False
        if not self._iziqo_siret():
            return False

        scope = self.env["iziqo.connector"]._iziqo_params()["scope"]
        if scope == "flagged":
            return bool(self._iziqo_get("x_studio_iziqo_1"))
        if scope == "customers":
            return self.customer_rank > 0
        # customers_and_prospects : on exclut les fournisseurs purs, ce qui
        # permet de pousser un nouveau client des sa creation (customer_rank
        # ne passe a 1 qu'a la premiere vente).
        return self.customer_rank > 0 or self.supplier_rank == 0

    def _iziqo_enqueue(self, operation=None, origin="auto"):
        """Cree (ou reutilise) un job par fiche et renvoie les ids."""
        Job = self.env["iziqo.sync.job"].sudo()
        job_ids = []
        for partner in self:
            wanted = operation or ("update" if partner.iziqo_last_sync_date else "create")
            if wanted == "create" and partner.iziqo_last_sync_date:
                # Fiche deja connue d'Iziqo (ex. ajout d'une adresse de
                # livraison sur une societe existante) : c'est une mise a jour.
                wanted = "update"
            job = Job.search(
                [("partner_id", "=", partner.id), ("state", "=", "pending")],
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
                        "partner_id": partner.id,
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
        for partner in self:
            partner.sudo().with_context(iziqo_sync_skip=True).write({
                "iziqo_last_sync_date": fields.Datetime.now(),
                "iziqo_last_sync_status": "success" if success else "error",
                "iziqo_last_sync_error": False if success else error_message,
            })

    # -------------------------------------------------------------------------
    # Payload
    # -------------------------------------------------------------------------

    def _iziqo_payload(self, operation="update"):
        """Reprend les colonnes du fichier clients Iziqo historique
        (voir fma_custom.action_export_iziqo_customers) afin que le mapping
        cote Iziqo reste inchange."""
        self.ensure_one()
        delivery = self._iziqo_delivery_address()
        commercial = self._iziqo_get("x_studio_commercial_1")

        return {
            "operation": operation,
            "odoo_id": self.id,
            "code_client": self.ref or "",
            "nom": self.name or "",
            "telephone": self.phone or "",
            "email": self.email or "",
            "siret": self._iziqo_siret(),
            "tva": self.vat or "",
            "adresse": ", ".join(p for p in [self.street or "", self.street2 or ""] if p),
            "cp": self.zip or "",
            "ville": self.city or "",
            "pays": self.country_id.name or "",
            "code_pays": self.country_id.code or "",
            "commercial": commercial.name if commercial else "",
            "id_employe_commercial": str(commercial.id) if commercial else "",
            "adresse_livraison": ", ".join(
                p for p in [delivery.street or "", delivery.street2 or ""] if p
            ),
            "cp_livraison": delivery.zip or "",
            "ville_livraison": delivery.city or "",
            "pays_livraison": delivery.country_id.name or "",
            "actif": bool(self.active),
            "date_modification": fields.Datetime.to_string(self.write_date) or "",
        }

    def _iziqo_delivery_address(self):
        """Adresse de livraison de la societe, avec repli sur la fiche elle-meme."""
        self.ensure_one()
        delivery = self.child_ids.filtered(lambda c: c.type == "delivery")[:1]
        return delivery or self

    def _iziqo_siret(self):
        """SIRET : `company_registry` en v19, avec repli sur les anciens champs
        (`siret` de l10n_fr, `x_studio_siret`) selon la base."""
        self.ensure_one()
        return (
            self._iziqo_get("siret")
            or self._iziqo_get("x_studio_siret")
            or self.company_registry
            or ""
        )

    def _iziqo_get(self, field_name):
        """Lecture tolerante d'un champ optionnel (champs Studio, l10n_fr...)."""
        self.ensure_one()
        if field_name in self._fields:
            return self[field_name]
        return False

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_iziqo_sync_now(self):
        """Bouton de la fiche client / action de liste.

        Sert notamment aux clients historiques : la selection est envoyee meme
        si elle sort du perimetre automatique (scope), la seule condition etant
        d'etre une societe avec un SIRET et de ne pas etre exclue.
        """
        if not self.env["iziqo.connector"]._iziqo_is_configured():
            raise UserError(
                _("L'URL de l'API Iziqo n'est pas configurée (Paramètres > Iziqo).")
            )

        companies = self.filtered("is_company")
        if not companies:
            raise UserError(_("Seules les sociétés sont synchronisées vers Iziqo."))

        excluded = companies.filtered("iziqo_sync_excluded")
        without_siret = (companies - excluded).filtered(lambda p: not p._iziqo_siret())
        targets = companies - excluded - without_siret

        if not targets:
            if without_siret:
                raise UserError(
                    _(
                        "SIRET manquant sur : %s.\n\nIziqo identifie les clients "
                        "par leur SIRET : renseignez-le avant de synchroniser."
                    )
                    % ", ".join(without_siret.mapped("display_name"))
                )
            raise UserError(_("Les fiches sélectionnées sont exclues de la synchro Iziqo."))

        job_ids = targets._iziqo_enqueue(origin="manual")
        self.env["iziqo.sync.job"].sudo().browse(job_ids)._process()

        errors = targets.filtered(lambda p: p.iziqo_last_sync_status == "error")
        if errors:
            message = _("Échec de la synchronisation de %(failed)s fiche(s) sur %(total)s.") % {
                "failed": len(errors),
                "total": len(targets),
            }
        else:
            message = _("%s fiche(s) synchronisée(s) vers Iziqo.") % len(targets)
        ignored = len(without_siret) + len(excluded)
        if ignored:
            message += _(" %s fiche(s) ignorée(s) (SIRET manquant ou fiche exclue).") % ignored
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
    def action_iziqo_sync_all(self):
        """Synchronisation complete : met en file tout le perimetre.

        L'envoi est laisse au cron de rattrapage pour ne pas bloquer la session.
        Renvoie le nombre de fiches mises en file et le nombre de societes
        ecartees faute de SIRET.
        """
        partners = self.sudo().with_context(active_test=False).search([
            ("is_company", "=", True),
            ("iziqo_sync_excluded", "=", False),
        ])
        targets = partners.filtered(lambda p: p._iziqo_is_eligible())
        missing_siret = partners.filtered(lambda p: not p._iziqo_siret())
        job_ids = targets._iziqo_enqueue(origin="full")
        _logger.info(
            "Iziqo: %s fiche(s) mise(s) en file, %s société(s) sans SIRET écartée(s).",
            len(job_ids),
            len(missing_siret),
        )
        return {"queued": len(job_ids), "missing_siret": len(missing_siret)}
