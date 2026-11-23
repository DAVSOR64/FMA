# -*- coding: utf-8 -*-
"""Le detail des coupes, que la nomenclature ne sait pas porter.

UNE NOMENCLATURE DIT UN BESOIN, PAS UN PLAN DE COUPE. La ligne de debit d'une
menuiserie dit « 11,076 m de T591007 en T7016.370 » : c'est juste, c'est ce
qu'il faut acheter et valoriser, et c'est inutilisable a la scie. L'atelier,
lui, a besoin de savoir que ces 11,076 m sont huit coupes, de 2,092 m a
0,316 m.

Le detail existait dans le fichier et se perdait a l'import : il etait cumule
par (reference, teinte) et le reste partait a la poubelle. Il vit desormais
ici, EN METRES comme tout le reste depuis le 23/11/2026, et se lit des deux
cotes :

* sur le LOT, a cote du besoin matiere — c'est l'ecran de la production, et
  les coupes y completent le plan de debit ;
* sur l'ARTICLE DE DEBIT de chaque menuiserie, a cote de sa nomenclature —
  c'est l'ecran des methodes, et les coupes y expliquent le besoin.

Rien n'est calcule ici : ces lignes ne nourrissent aucun ordre de fabrication
et ne sont consommees par personne. Elles sont la pour etre LUES.
"""
from odoo import api, fields, models


class FmaLotCutLine(models.Model):
    _name = "fma.lot.cut.line"
    _description = "Coupe du plan de debit"
    _order = "lot_id, product_id, length desc, id"

    lot_id = fields.Many2one(
        "fma.lot.fabrication",
        string="Lot",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        related="lot_id.company_id",
        store=True,
        index=True,
    )
    product_debit_id = fields.Many2one(
        "product.product",
        string="Ensemble debite",
        index=True,
        help="L'article de debit de la menuiserie a laquelle cette coupe "
        "appartient. Le fichier rattache chaque coupe a sa position.",
    )
    # LE RATTACHEMENT AU MODELE, et pas seulement a la variante. Un onglet sur
    # la fiche article vit sur product.template : sans cette colonne, aucune
    # relation un-vers-plusieurs ne peut s'y accrocher.
    product_debit_tmpl_id = fields.Many2one(
        "product.template",
        string="Modele de l'ensemble debite",
        related="product_debit_id.product_tmpl_id",
        store=True,
        index=True,
    )
    menuiserie = fields.Char(
        string="Menuiserie",
        help="Le repere tel que le pricer le nomme.",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Profile",
        required=True,
        index=True,
    )
    color = fields.Char(string="Teinte")
    length = fields.Float(
        string="Longueur (m)",
        digits="Product Unit of Measure",
        help="Longueur d'UNE coupe, en metres.",
    )
    qty = fields.Float(
        string="Coupes",
        default=1.0,
        digits="Product Unit of Measure",
        help="Nombre de coupes de cette longueur.",
    )
    total_length = fields.Float(
        string="Total (m)",
        compute="_compute_total_length",
        store=True,
        digits="Product Unit of Measure",
    )

    @api.depends("length", "qty")
    def _compute_total_length(self):
        for line in self:
            line.total_length = line.length * line.qty
