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
    fma_est_menuiserie = fields.Boolean(
        string="Menuiserie",
        compute="_compute_fma_est_menuiserie",
        store=True,
        help="Une menuiserie a une largeur et une hauteur. Un habillage — "
        "« Position matiere » cote LOGIKAL — n'en a pas : il appartient au "
        "lot, il se debite avec lui, mais il ne recoit ni numero de serie, "
        "ni casier, ni etiquette.",
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

    @api.depends("product_id")
    def _compute_fma_est_menuiserie(self):
        for line in self:
            line.fma_est_menuiserie = bool(
                line.product_id and not line.display_type
                and line._fma_a_des_dimensions()
            )

    @api.depends("product_id", "product_id.type", "display_type")
    def _compute_is_lotable(self):
        """Une ligne a lotir appartient au LOT, menuiserie ou non.

        J'avais confondu deux notions sous ce seul drapeau, et le metier l'a
        releve : un habillage — « Position matiere » cote LOGIKAL — se debite
        AVEC le lot, a la meme date, et ses minutes de debit entrent dans
        l'ordre de debit du lot. L'ecarter du lot lui retirait son debit.

        Ce qu'il n'est pas, c'est une MENUISERIE : pas de numero de serie,
        pas de casier, pas d'etiquette. C'est fma_est_menuiserie qui le dit,
        et lui seul.

        Reste donc a ecarter ce qui n'entre pas en fabrication : les services
        et les combos, les articles marques « exclu du comptage des reperes »
        — eco-contribution, transport —, et plus generalement ce qui n'a NI
        dimensions NI nomenclature. Un habillage a une nomenclature : c'est
        ce qui le distingue d'une ligne de texte.
        """
        Bom = self.env["mrp.bom"]
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
            if line._fma_a_des_dimensions():
                line.is_lotable = True
                continue
            # Sans dimensions, il faut une nomenclature : elle porte la
            # matiere a debiter. Sans elle, il n'y a rien a fabriquer.
            line.is_lotable = bool(
                Bom._bom_find(line.product_id).get(line.product_id))

    def _fma_a_des_dimensions(self):
        """Le produit de cette ligne porte-t-il largeur ET hauteur ?"""
        self.ensure_one()
        produit = self.product_id
        for nom in ("x_studio_largeur_mm", "x_studio_hauteur_mm"):
            if nom not in produit._fields or not produit[nom]:
                return False
        return True
