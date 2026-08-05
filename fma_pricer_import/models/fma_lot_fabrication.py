# -*- coding: utf-8 -*-
"""Rattachement d'un lot Odoo au lot du pricer."""
from odoo import fields, models


class FmaLotFabrication(models.Model):
    _inherit = "fma.lot.fabrication"

    pricer_lot_key = fields.Char(
        string="Cle du lot pricer",
        index=True,
        copy=False,
        help="Identifiant du lot chez le pricer (GUID de la phase LOGIKAL). "
        "Sert a retrouver le lot lors d'un reimport : redeposer le fichier "
        "d'un lot corrige met a jour ce lot-la et ne touche pas aux autres.",
    )
