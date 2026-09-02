# -*- coding: utf-8 -*-
"""Synchronisation des sociétés clientes vers Iziqo.

La mecanique (declenchement, file, envoi post-commit, relances) vient de
iziqo.sync.mixin. Ce fichier ne porte que ce qui est propre au client :
perimetre, payload et identifiants.
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _name = "res.partner"
    _inherit = ["res.partner", "iziqo.sync.mixin"]

    _iziqo_url_param = "iziqo_sync.api_url"
    _iziqo_identifier_param = "iziqo_sync.identifier_field"
    _iziqo_default_identifier = "id"
    # Champs du payload, plus ceux qui pilotent l'appartenance au perimetre.
    _iziqo_tracked_fields = frozenset({
        "active",
        "city",
        "company_registry",
        "country_id",
        "customer_rank",
        "email",
        "is_company",
        "iziqo_sync_excluded",
        "name",
        "parent_id",
        "phone",
        "ref",
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
    })

    # -------------------------------------------------------------------------
    # Perimetre
    # -------------------------------------------------------------------------

    def _iziqo_is_eligible(self):
        """Perimetre : societes avec SIRET, filtrees par iziqo_sync.scope.

        Le SIRET est la donnee de rapprochement attendue cote Iziqo : une
        fiche sans SIRET n'est jamais envoyee, elle le sera automatiquement
        des que le SIRET sera renseigne (le champ est suivi).
        """
        self.ensure_one()
        if self.iziqo_sync_excluded or not self.is_company:
            return False
        if not self._iziqo_siret():
            return False

        scope = self.env["ir.config_parameter"].sudo().get_param(
            "iziqo_sync.scope"
        ) or "customers_and_prospects"
        if scope == "flagged":
            return bool(self._iziqo_get("x_studio_iziqo_1"))
        if scope == "customers":
            return self.customer_rank > 0
        # customers_and_prospects : on exclut les fournisseurs purs, ce qui
        # permet de pousser un nouveau client des sa creation (customer_rank
        # ne passe a 1 qu'a la premiere vente).
        return self.customer_rank > 0 or self.supplier_rank == 0

    def _iziqo_targets(self):
        """Fiches a pousser : les societes eligibles du recordset, et la
        societe parente quand c'est une adresse de livraison ou de
        facturation qui bouge (elle alimente les colonnes "... livraison")."""
        targets = self.env["res.partner"]
        for partner in self:
            if partner._iziqo_is_eligible():
                targets |= partner
            elif partner.parent_id and partner.type in ("delivery", "invoice"):
                if partner.parent_id._iziqo_is_eligible():
                    targets |= partner.parent_id
        return targets

    def _iziqo_manual_targets(self):
        """Bouton manuel : le perimetre automatique est ignore, ce qui sert
        aux clients historiques. Restent obligatoires : etre une societe,
        avoir un SIRET, ne pas etre exclue."""
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
        return targets

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

    def _iziqo_identifier_candidates(self):
        self.ensure_one()
        return {
            "id": str(self.id),
            "siret": self._iziqo_siret(),
            "ref": self.ref or "",
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

    @api.model
    def action_iziqo_sync_all(self):
        """Synchronisation complete des clients. L'envoi est laisse au cron.

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
            "Iziqo: %s client(s) mis en file, %s société(s) sans SIRET écartée(s).",
            len(job_ids),
            len(missing_siret),
        )
        return {"queued": len(job_ids), "missing_siret": len(missing_siret)}
