# -*- coding: utf-8 -*-
"""Besoin matiere d'un lot (profiles, renforts, accessoires debites).

Alimente les composants de l'OF Debit lorsque l'article debite n'a pas de
nomenclature dediee, et sert de base aux approvisionnements par lot.
"""
from odoo import api, fields, models


class FmaLotMaterialLine(models.Model):
    _name = "fma.lot.material.line"
    _description = "Besoin matiere d'un lot de fabrication"
    _order = "lot_id, sequence, id"

    sequence = fields.Integer(string="Sequence", default=10)
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
    product_id = fields.Many2one(
        "product.product",
        string="Article",
        required=True,
        domain="[('type', '=', 'consu')]",
    )
    product_qty = fields.Float(
        string="Quantite",
        default=1.0,
        required=True,
        digits="Product Unit of Measure",
    )
    product_uom_id = fields.Many2one(
        "uom.uom",
        string="Unite",
        compute="_compute_product_uom_id",
        store=True,
        readonly=False,
        required=True,
    )
    note = fields.Char(string="Note")

    _material_qty_positive = models.Constraint(
        "CHECK(product_qty > 0)",
        "La quantité doit être strictement positive.",
    )

    @api.depends("product_id")
    def _compute_product_uom_id(self):
        # Un compute doit affecter une valeur a *chaque* enregistrement traite :
        # sortir de la boucle sans rien ecrire laisse un champ requis vide, et
        # la creation echoue sur « Valeur requise manquante pour le champ
        # Unite ». On affecte donc dans les deux cas.
        for line in self:
            line.product_uom_id = line.product_id.uom_id or False
