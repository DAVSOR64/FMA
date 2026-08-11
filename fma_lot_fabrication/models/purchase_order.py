# -*- coding: utf-8 -*-
"""Rattachement des achats aux lots de fabrication.

Le lien vit sur la LIGNE d'achat, pas sur l'en-tete. C'est la regle metier
qui l'impose : une barre optimisee dans un lot ne sert pas ailleurs, mais un
bon de commande regroupe les besoins de plusieurs lots des lors qu'ils
partagent le fournisseur et le projet. Un lien porte par l'en-tete forcerait
un PO par lot, ou perdrait tous les lots sauf un.

L'en-tete porte donc la liste des lots concernes, deduite de ses lignes.
"""
import re

from odoo import api, fields, models

# Jetons plausibles d'une reference de lot dans un champ "origin" libre.
ORIGIN_TOKEN_RE = re.compile(r"[A-Za-z0-9_/\-]+")


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    lot_fabrication_id = fields.Many2one(
        "fma.lot.fabrication",
        string="Lot de fabrication",
        compute="_compute_lot_fabrication_id",
        store=True,
        readonly=False,
        index="btree_not_null",
        ondelete="set null",
        help="Lot a l'origine de ce besoin. Renseigne automatiquement quand "
        "la ligne provient d'un OF du lot, modifiable manuellement.",
    )

    @api.depends(
        "move_dest_ids.raw_material_production_id.lot_fabrication_id",
        "order_id.origin",
    )
    def _compute_lot_fabrication_id(self):
        Lot = self.env["fma.lot.fabrication"]
        for line in self:
            # 1. Via les mouvements de destination -> OF -> lot.
            lot = line.move_dest_ids.raw_material_production_id.lot_fabrication_id[:1]

            # 2. Repli : la reference de lot figure dans l'origine du PO. Les
            #    regles de reappro y recopient la reference de l'OF ou du lot
            #    selon les configurations.
            if not lot and line.order_id.origin:
                jetons = ORIGIN_TOKEN_RE.findall(line.order_id.origin)
                if jetons:
                    lot = Lot.search(
                        [
                            ("name", "in", jetons),
                            ("company_id", "=", line.order_id.company_id.id),
                        ],
                        limit=1,
                    )

            # Une affectation manuelle fait foi. L'affectation est
            # inconditionnelle : un compute stocke doit donner une valeur a
            # CHAQUE enregistrement, sans quoi Odoo leve « failed to assign ».
            line.lot_fabrication_id = line.lot_fabrication_id or lot


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    lot_fabrication_ids = fields.Many2many(
        "fma.lot.fabrication",
        string="Lots de fabrication",
        compute="_compute_lot_fabrication_ids",
        store=True,
        help="Lots dont ce bon de commande couvre les besoins.",
    )

    @api.depends("order_line.lot_fabrication_id")
    def _compute_lot_fabrication_ids(self):
        for order in self:
            order.lot_fabrication_ids = order.order_line.lot_fabrication_id

    # Ancien lien d'en-tete. Conserve declare et retire des ecrans : il ne
    # pouvait porter qu'un lot, ce qui interdisait le regroupement des achats.
    # Sa suppression viendra dans une version ulterieure — retirer un champ et
    # sa reference en vue dans la meme mise a jour fait echouer le
    # deploiement, les vues etant validees une par une.
    lot_fabrication_id = fields.Many2one(
        "fma.lot.fabrication",
        string="Lot de fabrication (obsolète)",
        index="btree_not_null",
        ondelete="set null",
    )

    def action_view_lot_fabrication(self):
        self.ensure_one()
        lots = self.lot_fabrication_ids
        if not lots:
            return False
        action = {
            "type": "ir.actions.act_window",
            "name": "Lots de fabrication",
            "res_model": "fma.lot.fabrication",
        }
        if len(lots) == 1:
            action.update({"res_id": lots.id, "view_mode": "form"})
        else:
            action.update({
                "domain": [("id", "in", lots.ids)],
                "view_mode": "list,form",
            })
        return action
