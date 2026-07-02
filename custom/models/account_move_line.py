# -*- coding: utf-8 -*-
"""Champs migrés depuis Odoo Studio (staging DB, audité 2026-07-02).
Noms techniques conservés à l'identique, aucune migration de données.
12 champs volontairement exclus (voir STUDIO_AUDIT.md) : related_field_*
(cible non vérifiable), sélection à valeurs inconnues, ou non stockés.
"""
from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    x_studio_activit = fields.Char(string="Activité", readonly=True)
    x_studio_affaire = fields.Char(string="Affaire", readonly=True)
    x_studio_position = fields.Char(string="Position", readonly=True)
