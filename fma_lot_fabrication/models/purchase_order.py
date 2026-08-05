# -*- coding: utf-8 -*-
"""Rattachement des achats a un lot de fabrication.

Les appros se font au niveau du lot (et non ligne a ligne). Le lien est
etabli en priorite par le groupe d'approvisionnement du lot, avec repli sur
le champ ``origin`` — les regles de reappro y recopient la reference de l'OF
ou du lot selon les configurations.
"""
import re

from odoo import api, fields, models

# Jetons plausibles d'une reference de lot dans un champ "origin" libre.
ORIGIN_TOKEN_RE = re.compile(r"[A-Za-z0-9_/\-]+")


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    lot_fabrication_id = fields.Many2one(
        "fma.lot.fabrication",
        string="Lot de fabrication",
        compute="_compute_lot_fabrication_id",
        store=True,
        readonly=False,
        index=True,
        ondelete="set null",
        help="Lot a l'origine de cet approvisionnement. Renseigne "
        "automatiquement quand l'achat provient d'un OF du lot, modifiable "
        "manuellement.",
    )

    @api.depends("origin", "order_line.move_dest_ids")
    def _compute_lot_fabrication_id(self):
        Lot = self.env["fma.lot.fabrication"]
        for order in self:
            if order.lot_fabrication_id:
                # Ne jamais ecraser une affectation, manuelle ou deja calculee.
                # Reassignation explicite : un compute stocke doit toujours
                # affecter une valeur a chaque enregistrement du lot traite.
                order.lot_fabrication_id = order.lot_fabrication_id
                continue

            # 1. Via les mouvements de destination -> OF -> lot.
            productions = order.order_line.mapped(
                "move_dest_ids.raw_material_production_id"
            )
            lot = productions.mapped("lot_fabrication_id")[:1]

            # 2. Repli : la reference de lot figure dans l'origine.
            if not lot and order.origin:
                tokens = ORIGIN_TOKEN_RE.findall(order.origin)
                if tokens:
                    lot = Lot.search(
                        [
                            ("name", "in", tokens),
                            ("company_id", "=", order.company_id.id),
                        ],
                        limit=1,
                    )

            order.lot_fabrication_id = lot

    def action_view_lot_fabrication(self):
        self.ensure_one()
        if not self.lot_fabrication_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "name": "Lot de fabrication",
            "res_model": "fma.lot.fabrication",
            "res_id": self.lot_fabrication_id.id,
            "view_mode": "form",
        }
