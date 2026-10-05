# -*- coding: utf-8 -*-
"""Synchronisation des commerciaux vers Iziqo.

Meme mecanique que les clients (iziqo.sync.mixin), sur une collection Iziqo
distincte. L'ID Odoo de l'employe est la cle de jointure : c'est la valeur
envoyee dans « id_employe_commercial » du payload client, et Iziqo en fait le
code du commercial chez le fabricant.
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

DEFAULT_DEPARTMENT = "Commerce"


class HrEmployee(models.Model):
    _name = "hr.employee"
    _inherit = ["hr.employee", "iziqo.sync.mixin"]

    _iziqo_url_param = "iziqo_sync.employee_api_url"
    # Aucun identifiant configurable : Iziqo refuse en 400 tout PATCH dont
    # l'identifiant d'URL differe du « odoo_id » du payload.
    _iziqo_identifier_param = None
    _iziqo_default_identifier = "id"
    # La collection commerciaux n'expose pas de GET, contrairement aux clients.
    _iziqo_supports_get = False
    _iziqo_tracked_fields = frozenset({
        "active",
        "barcode",
        "department_id",
        "iziqo_sync_excluded",
        "job_title",
        "mobile_phone",
        "name",
        "work_email",
        "work_phone",
    })

    # Champs du mixin reserves aux RH. Pour les autres utilisateurs, Odoo lit
    # hr.employee au travers de hr.employee.public et refuse tout champ absent
    # de ce profil public : sans groupe, ces champs entraient dans le prefetch
    # et le pointage tombait en « Erreur d'acces ». Le groupe les en exclut,
    # comme les champs prives natifs de hr.employee.
    iziqo_sync_excluded = fields.Boolean(groups="hr.group_hr_user")
    iziqo_last_sync_date = fields.Datetime(groups="hr.group_hr_user")
    iziqo_last_sync_status = fields.Selection(groups="hr.group_hr_user")
    iziqo_last_sync_error = fields.Text(groups="hr.group_hr_user")

    # -------------------------------------------------------------------------
    # Perimetre
    # -------------------------------------------------------------------------

    def _iziqo_is_in_scope(self):
        """Perimetre configure, e-mail mis a part.

        Le filtre porte sur le nom du departement et non sur son id, qui
        differe d'un environnement a l'autre -- meme raison que le domaine de
        res.partner.x_studio_commercial_1.
        """
        self.ensure_one()
        get_param = self.env["ir.config_parameter"].sudo().get_param
        scope = get_param("iziqo_sync.employee_scope") or "department"
        if scope == "all":
            return True
        department = (get_param("iziqo_sync.employee_department") or DEFAULT_DEPARTMENT).strip()
        return self.department_id.name == department

    def _iziqo_is_eligible(self):
        """Perimetre automatique : commerciaux du perimetre ayant un e-mail.

        L'e-mail professionnel est obligatoire cote Iziqo, qui refuse la fiche
        en 400 sans lui : c'est par lui qu'il reconnait un commercial deja
        connu pour un autre fabricant. Une fiche sans e-mail est donc ignoree,
        puis envoyee des qu'il est renseigne, work_email etant un champ suivi.
        """
        self.ensure_one()
        if self.iziqo_sync_excluded or not self._iziqo_email():
            return False
        return self._iziqo_is_in_scope()

    def _iziqo_email(self):
        self.ensure_one()
        return (self.work_email or "").strip()

    def _iziqo_manual_targets(self):
        """Bouton manuel : envoie l'employe meme hors du departement
        commercial, ce qui sert aux commerciaux historiques rattaches
        ailleurs. Restent obligatoires : ne pas etre exclu, avoir un e-mail."""
        candidates = self.filtered(lambda e: not e.iziqo_sync_excluded)
        without_email = candidates.filtered(lambda e: not e._iziqo_email())
        targets = candidates - without_email

        if not targets:
            if without_email:
                raise UserError(
                    _(
                        "E-mail professionnel manquant sur : %s.\n\nIziqo "
                        "identifie le commercial par son e-mail et refuse la "
                        "fiche sans lui."
                    )
                    % ", ".join(without_email.mapped("display_name"))
                )
            raise UserError(
                _("Les fiches sélectionnées sont exclues de la synchro Iziqo.")
            )
        return targets

    # -------------------------------------------------------------------------
    # Payload
    # -------------------------------------------------------------------------

    def _iziqo_payload(self, operation="update"):
        """« odoo_id » est la cle de jointure avec « id_employe_commercial »
        du payload client. « nom » et « email » ne peuvent pas etre vides,
        Iziqo les refusant en 400 ; les autres cles sont facultatives et
        « fonction » n'est pas exploitee, la qualification TCI / RRV etant un
        reglage Iziqo."""
        self.ensure_one()
        return {
            "operation": operation,
            "odoo_id": self.id,
            "nom": (self.name or "").strip(),
            "email": self._iziqo_email(),
            "telephone": (self.work_phone or "").strip(),
            "mobile": (self.mobile_phone or "").strip(),
            "fonction": (self.job_title or "").strip(),
            "departement": self.department_id.name or "",
            "matricule": (self.barcode or "").strip(),
            "actif": bool(self.active),
            "date_modification": fields.Datetime.to_string(self.write_date) or "",
        }

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    @api.model
    def action_iziqo_sync_all_employees(self):
        """Synchronisation complete des commerciaux, envoi laisse au cron.

        Renvoie le nombre de fiches mises en file et le nombre de commerciaux
        du perimetre ecartes faute d'e-mail.
        """
        employees = self.sudo().with_context(active_test=False).search([
            ("iziqo_sync_excluded", "=", False),
        ])
        in_scope = employees.filtered(lambda e: e._iziqo_is_in_scope())
        targets = in_scope.filtered(lambda e: e._iziqo_email())
        missing_email = in_scope - targets
        job_ids = targets._iziqo_enqueue(origin="full")
        _logger.info(
            "Iziqo: %s commercial/commerciaux mis en file, %s sans e-mail écarté(s).",
            len(job_ids),
            len(missing_email),
        )
        return {"queued": len(job_ids), "missing_email": len(missing_email)}
