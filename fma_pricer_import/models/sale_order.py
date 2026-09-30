# -*- coding: utf-8 -*-
"""Bouton Import Pricer sur le devis."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    pricer_import_ids = fields.One2many(
        "sqlite.connector",
        "target_sale_order_id",
        string="Imports Pricer",
        readonly=True,
    )
    pricer_import_count = fields.Integer(
        string="Nb imports",
        compute="_compute_pricer_import_count",
    )

    @api.depends("pricer_import_ids")
    def _compute_pricer_import_count(self):
        for order in self:
            order.pricer_import_count = len(order.pricer_import_ids)

    #: Etats ou deposer un chiffrage reste possible.
    #:
    #: « validated » y figure : chez FMA la validation est une etape INTERNE,
    #: entre le devis et la confirmation — le devis est relu, pas vendu. Le
    #: chiffrage continue d'evoluer jusqu'a la commande, et l'exclure obligeait
    #: a devalider le devis pour redeposer un fichier corrige.
    #:
    #: La confirmation, elle, reste la limite : au-dela il y a des OF, des
    #: achats et des lots, et reimporter reecrirait des lignes que la
    #: production suit deja.
    ETATS_IMPORT_PRICER = ("draft", "sent", "validated")

    def _pricer_import_autorise(self):
        """Leve si l'etat du devis interdit le depot d'un chiffrage.

        Porte par la commande et non par le wizard : les deux points d'entree
        — le menu Action et le bouton du wizard — doivent appliquer la meme
        regle, et une regle ecrite deux fois finit par differer.
        """
        self.ensure_one()
        if self.state in self.ETATS_IMPORT_PRICER:
            return True
        raise UserError(
            _(
                "Le devis %(name)s est confirme : l'import Pricer n'est plus "
                "possible.\n\n"
                "Des ordres de fabrication, des achats et des lots suivent "
                "desormais ces lignes ; les reecrire depuis un fichier les "
                "laisserait en desaccord avec la production.",
                name=self.display_name,
            )
        )

    def action_open_pricer_import(self):
        """Ouvre le wizard de depot du fichier de chiffrage."""
        self.ensure_one()
        self._pricer_import_autorise()
        return {
            "type": "ir.actions.act_window",
            "name": _("Import Pricer - %s", self.name),
            "res_model": "fma.pricer.import.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_order_id": self.id,
                "default_description": _("Import Pricer %s", self.name),
            },
        }

    def action_view_pricer_imports(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Imports Pricer"),
            "res_model": "sqlite.connector",
            "domain": [("target_sale_order_id", "=", self.id)],
            "view_mode": "list,form",
        }
