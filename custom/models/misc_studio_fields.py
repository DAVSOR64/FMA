# -*- coding: utf-8 -*-
"""Champs Studio isolés (1-2 champs par modèle) migrés depuis Odoo Studio
(staging DB, audité 2026-07-02). Noms techniques conservés à l'identique,
aucune migration de données. Regroupés dans un seul fichier plutôt que
répartis sur 6 fichiers d'un seul champ chacun.
"""
from odoo import fields, models


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    x_studio_datetime_field_4k_1j9c640h6 = fields.Datetime(string="Nouveau Datetime")
    x_studio_intervention = fields.Integer(string="Intervention")


class ProductCategory(models.Model):
    _inherit = "product.category"

    x_studio_logical_map = fields.Char(string="Logical map")
    x_studio_logikal_map = fields.Char(string="Logikal map")


class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    x_studio_catgorie_de_produit_mtn = fields.Many2one(
        "product.category", string="Catégorie de produit", readonly=True
    )


class AccountPaymentTerm(models.Model):
    _inherit = "account.payment.term"

    x_studio_code = fields.Char(string="code")


class MrpWorkcenterProductivity(models.Model):
    _inherit = "mrp.workcenter.productivity"

    x_studio_affaire = fields.Char(string="Affaire", readonly=True)


class UomUom(models.Model):
    _inherit = "uom.uom"

    x_studio_uom_logical = fields.Char(string="Uom Logical")
