# -*- coding: utf-8 -*-
"""Mesure du debit : ce qu'on achete en barres, ce qu'on consomme en metres."""
from odoo import api, fields, models


class FmaLotMaterialLine(models.Model):
    _inherit = "fma.lot.material.line"

    bar_length = fields.Float(
        string="Longueur de barre (m)",
        digits="Product Unit of Measure",
        help="Longueur de la barre achetee, telle que le pricer l'a optimisee.",
    )
    debit_length = fields.Float(
        string="Besoin debit (m)",
        digits="Product Unit of Measure",
        help="Metres lineaires reellement necessaires aux menuiseries du lot, "
        "somme des coupes du plan de debit. C'est ce qui entre en en-cours ; "
        "la difference avec les barres achetees est la chute.",
    )
    purchased_length = fields.Float(
        string="Achete (m)",
        compute="_compute_lengths",
        store=True,
        digits="Product Unit of Measure",
    )
    loss_length = fields.Float(
        string="Chute (m)",
        compute="_compute_lengths",
        store=True,
        digits="Product Unit of Measure",
    )
    loss_rate = fields.Float(
        string="Chute (%)",
        compute="_compute_lengths",
        store=True,
        digits=(5, 1),
    )

    @api.depends("product_qty", "bar_length", "debit_length")
    def _compute_lengths(self):
        for line in self:
            achete = line.product_qty * line.bar_length
            line.purchased_length = achete
            line.loss_length = achete - line.debit_length
            line.loss_rate = (
                100.0 * line.loss_length / achete if achete else 0.0
            )
