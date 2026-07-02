# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Real model replacing the Odoo Studio "manual" model
x_account_move_line_803a2, plus the one2many field Studio added on
account.move to expose it (staging DB, audited 2026-07-02).
See STUDIO_AUDIT.md at the repo root -- this model only has a
name/sequence skeleton, no other business field was ever added to it.
"""
from odoo import fields, models


class XAccountMoveLine803a2(models.Model):
    _name = "x_account_move_line_803a2"
    _description = "Account Move Line (Studio)"

    x_account_move_id = fields.Many2one("account.move", string="Facture / Écriture")
    x_name = fields.Char(string="Description", required=True)
    x_studio_sequence = fields.Integer(string="Séquence")


class AccountMove(models.Model):
    _inherit = "account.move"

    x_studio_one2many_field_kJvUD = fields.One2many(
        "x_account_move_line_803a2", "x_account_move_id", string="New Lines"
    )
