# -*- coding: utf-8 -*-
"""Champs migrés depuis Odoo Studio (staging DB, audité 2026-07-02).
Noms techniques conservés à l'identique, aucune migration de données.
"""
from odoo import fields, models


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    x_studio_forme = fields.Char(string="Forme", readonly=True)
    x_studio_posit = fields.Char(string="Position/N°")
    x_studio_position = fields.Char(string="position", readonly=True)
    x_studio_spacer = fields.Char(string="spacer")
    x_studio_spacer_2 = fields.Char(string="Spacer", readonly=True)
    # Dimensions vitrage : initialement exclues du portage (supposées non
    # stockées côté Studio), mais vérification en base le 2026-07-16 confirme
    # qu'elles existent et sont massivement renseignées (~16 865 / 16 861
    # lignes) et sont utilisées par le rapport "Bon de commande Remplissage"
    # et l'export XML v2. On les sécurise donc en code (type Integer confirmé
    # en base, mêmes valeurs, aucune migration). Exposition en vue à trancher
    # séparément avec le métier.
    x_studio_hauteur = fields.Integer(string="Hauteur")
    x_studio_largeur = fields.Integer(string="Largeur")
