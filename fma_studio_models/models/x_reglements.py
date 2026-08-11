# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Real model replacing the Odoo Studio "manual" model x_reglements. See
STUDIO_AUDIT.md at the repo root -- this model only has a
name/libelle/sequence skeleton in Studio, no amount, date or
payment-related field was ever added to it.
"""
from odoo import api, fields, models


class XReglements(models.Model):
    _name = "x_reglements"
    _description = "Règlements"
    _rec_name = "x_name"
    _order = "x_studio_sequence, id"

    x_active = fields.Boolean(string="Actif", default=True)
    x_name = fields.Char(string="Description", required=True, translate=True)
    x_studio_libelle = fields.Char(string="Libelle")
    x_studio_sequence = fields.Integer(string="Séquence")

    @api.depends("x_name", "x_studio_libelle")
    def _compute_display_name(self):
        """Affiche le code ET le libelle partout ou le mode est choisi.

        Sur la fiche client comme sur le devis, « 11 » seul ne dit rien a
        personne. Les deux colonnes du referentiel etant faites pour ca, on
        les montre ensemble des que la seconde est renseignee.
        """
        for reglement in self:
            if reglement.x_studio_libelle:
                reglement.display_name = "%s - %s" % (
                    reglement.x_name or "",
                    reglement.x_studio_libelle,
                )
            else:
                reglement.display_name = reglement.x_name or ""
