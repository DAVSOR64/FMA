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
        "order_id.order_line.product_id",
    )
    def _compute_is_lotable(self):
        """Une ligne a lotir est une MENUISERIE, pas une fourniture.

        UNE MENUISERIE A UNE LARGEUR ET UNE HAUTEUR. C'est le critere le plus
        sur, et il vient de LOGIKAL : une elevation « chassis » porte ses
        dimensions, une « Position matiere » n'en a pas. Sur A26-10-07833, la
        ligne « Fourniture de cales de vitrage » etait une position matiere —
        elle est devenue la huitieme menuiserie du lot, avec son ordre
        d'assemblage, son numero de serie et son casier, et ne se planifiait
        pas comme les autres.

        La position du repere ne suffit pas : LOGIKAL en donne une AUSSI aux
        positions matiere (« TS N°1 », « 003 »). Elle ne sert donc que de
        second critere, pour les commandes ou les dimensions ne sont pas
        renseignees.

        Trois niveaux, du plus sur au plus large, et chacun ne s'applique que
        si la commande porte l'information : refuser tout lotissement sur une
        commande ancienne ou saisie a la main serait pire que d'en trop
        proposer.
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

            lignes = line.order_id.order_line.filtered(
                lambda l: not l.display_type and l.product_id)
            dimensionnees = lignes.filtered(lambda l: l._fma_a_des_dimensions())
            if dimensionnees:
                line.is_lotable = line._fma_a_des_dimensions()
                continue
            positionnees = lignes.filtered(
                lambda l: "x_studio_position" in l._fields
                and (l.x_studio_position or "").strip()
            )
            if positionnees:
                line.is_lotable = bool(
                    "x_studio_position" in line._fields
                    and (line.x_studio_position or "").strip())
                continue
            line.is_lotable = True

    def _fma_a_des_dimensions(self):
        """Le produit de cette ligne porte-t-il largeur ET hauteur ?"""
        self.ensure_one()
        produit = self.product_id
        for nom in ("x_studio_largeur_mm", "x_studio_hauteur_mm"):
            if nom not in produit._fields or not produit[nom]:
                return False
        return True
