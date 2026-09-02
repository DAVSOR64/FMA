# -*- coding: utf-8 -*-
"""Synchronisation des commerciaux vers Iziqo.

Meme mecanique que les clients (iziqo.sync.mixin), sur une collection Iziqo
distincte. L'ID Odoo de l'employe est la cle de jointure : c'est la valeur
envoyee dans « id_employe_commercial » du payload client.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

DEFAULT_DEPARTMENT = "Commerce"


class HrEmployee(models.Model):
    _name = "hr.employee"
    _inherit = ["hr.employee", "iziqo.sync.mixin"]

    _iziqo_url_param = "iziqo_sync.employee_api_url"
    _iziqo_identifier_param = "iziqo_sync.employee_identifier_field"
    _iziqo_default_identifier = "id"
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

    # -------------------------------------------------------------------------
    # Perimetre
    # -------------------------------------------------------------------------

    def _iziqo_is_eligible(self):
        """Par defaut, les employes du departement commercial.

        Le filtre porte sur le nom du departement et non sur son id, qui
        differe d'un environnement a l'autre -- meme raison que le domaine de
        res.partner.x_studio_commercial_1.
        """
        self.ensure_one()
        if self.iziqo_sync_excluded:
            return False

        get_param = self.env["ir.config_parameter"].sudo().get_param
        scope = get_param("iziqo_sync.employee_scope") or "department"
        if scope == "all":
            return True
        department = (get_param("iziqo_sync.employee_department") or DEFAULT_DEPARTMENT).strip()
        return self.department_id.name == department

    def _iziqo_manual_targets(self):
        """Bouton manuel : envoie l'employe meme hors du departement
        commercial, ce qui sert aux commerciaux historiques rattaches
        ailleurs. Seule condition : ne pas etre exclu."""
        targets = self.filtered(lambda e: not e.iziqo_sync_excluded)
        if not targets:
            raise UserError(
                _("Les fiches sélectionnées sont exclues de la synchro Iziqo.")
            )
        return targets

    # -------------------------------------------------------------------------
    # Payload
    # -------------------------------------------------------------------------

    def _iziqo_payload(self, operation="update"):
        """« odoo_id » est la cle de jointure avec « id_employe_commercial »
        du payload client."""
        self.ensure_one()
        return {
            "operation": operation,
            "odoo_id": self.id,
            "nom": self.name or "",
            "email": self.work_email or "",
            "telephone": self.work_phone or "",
            "mobile": self.mobile_phone or "",
            "fonction": self.job_title or "",
            "departement": self.department_id.name or "",
            "matricule": self.barcode or "",
            "actif": bool(self.active),
            "date_modification": fields.Datetime.to_string(self.write_date) or "",
        }

    def _iziqo_identifier_candidates(self):
        self.ensure_one()
        return {
            "id": str(self.id),
            "email": self.work_email or "",
            "matricule": self.barcode or "",
        }

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    @api.model
    def action_iziqo_sync_all_employees(self):
        """Synchronisation complete des commerciaux, envoi laisse au cron."""
        return {"queued": self._iziqo_sync_all()}
