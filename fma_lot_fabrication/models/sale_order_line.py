# -*- coding: utf-8 -*-
"""Vue lot sur la ligne de devis.

La ligne ne porte pas de lot en direct : elle peut etre repartie sur
plusieurs lots. On expose donc les liaisons, la quantite deja lotie et le
reste a lotir, qui pilotent le wizard de mise en lot.
"""
from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    lot_line_ids = fields.One2many(
        "fma.lot.fabrication.line",
        "sale_line_id",
        string="Lots de fabrication",
        copy=False,
    )
    lot_ids = fields.Many2many(
        "fma.lot.fabrication",
        string="Lots",
        compute="_compute_lot_info",
        store=False,
    )
    qty_lot = fields.Float(
        string="Quantite lotie",
        compute="_compute_lot_info",
        digits="Product Unit of Measure",
        help="Somme des quantites affectees a un lot de fabrication actif.",
    )
    qty_to_lot = fields.Float(
        string="Reste a lotir",
        compute="_compute_lot_info",
        digits="Product Unit of Measure",
    )
    is_lotable = fields.Boolean(
        string="A lotir",
        compute="_compute_is_lotable",
        store=True,
        help="Ligne eligible a la mise en lot : article stockable ou "
        "consommable, ni section ni note. Stocke pour rester filtrable "
        "dans les vues et les domaines.",
    )

    @api.depends(
        "lot_line_ids.product_qty",
        "lot_line_ids.lot_id.state",
        "product_uom_qty",
    )
    def _compute_lot_info(self):
        for line in self:
            active = line.lot_line_ids.filtered(
                lambda l: l.lot_id.state != "cancel"
            )
            line.lot_ids = active.mapped("lot_id")
            line.qty_lot = sum(active.mapped("product_qty"))
            line.qty_to_lot = max(line.product_uom_qty - line.qty_lot, 0.0)

    @api.depends(
        "product_id", "product_id.type", "display_type",
        "order_id.order_line.x_studio_position",
    )
    def _compute_is_lotable(self):
        """Une ligne a lotir est une MENUISERIE, pas n'importe quel bien.

        Le critere « article consommable » retenait tout : sur A26-10-07833,
        la ligne « Fourniture de cales de vitrage » — 100 pieces, aucune
        gamme — devenait une menuiserie du lot, avec son ordre d'assemblage,
        son numero de serie et son casier. Elle ne se planifiait pas comme
        les autres et son ordre ne portait que deux composants : c'est une
        fourniture, pas une ouverture.

        Le critere est donc la POSITION du repere, celui que l'ordonnancement
        emploie deja pour compter les reperes d'une affaire : les lignes
        menuiserie la portent (« Repère A - Entrée »), l'eco-contribution,
        la remise et les fournitures ne la portent pas. On ne s'invente pas
        une seconde definition de la menuiserie.

        Repli sur l'ancien critere quand AUCUNE ligne de la commande ne porte
        de position : sur ces commandes-la — anciennes, ou saisies a la main
        — refuser tout lotissement serait pire que d'en trop proposer.
        """
        for line in self:
            if line.display_type or not line.product_id:
                line.is_lotable = False
                continue
            # En v19 les articles stockables et consommables partagent le
            # type 'consu' (le stockage est porte par is_storable) ; seuls
            # les services et les combos sont a exclure.
            if line.product_id.type != "consu":
                line.is_lotable = False
                continue
            if "fma_exclu_reperes" in line.product_id._fields and (
                    line.product_id.fma_exclu_reperes):
                line.is_lotable = False
                continue
            if "x_studio_position" not in line._fields:
                line.is_lotable = True
                continue
            porteuses = line.order_id.order_line.filtered(
                lambda l: not l.display_type and l.product_id
                and (l.x_studio_position or "").strip()
            )
            line.is_lotable = (
                bool((line.x_studio_position or "").strip())
                if porteuses else True
            )
