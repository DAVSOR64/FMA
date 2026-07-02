# -*- coding: utf-8 -*-
"""Champs migrés depuis Odoo Studio (staging DB, audité 2026-07-02).
Noms techniques conservés à l'identique, aucune migration de données.
Plusieurs de ces champs (x_studio_color_logikal, x_studio_longueur_m,
x_studio_ref_int_logikal, x_studio_unit_logikal...) sont déjà consommés par
les gabarits d'export XML de purchase_order_export.
3 champs volontairement exclus (voir STUDIO_AUDIT.md) : related_field_*
(cible non vérifiable), ou one2many sans inverse_name confirmé.
"""
from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    x_studio_char_field_5cq_1j6cmccbl = fields.Char(string="Nouveau Texte")
    x_studio_char_field_7d1_1iv4rm5dn = fields.Char(string="Nouveau Texte")
    x_studio_code_tarifaire = fields.Char(string="Code tarifaire")
    x_studio_color_logikal = fields.Char(string="Color Logikal")
    x_studio_conso_laffaire = fields.Boolean(string="Conso à l'affaire?")
    x_studio_couleur_pb_intext = fields.Char(string="Couleur PB (Int/Ext)")
    x_studio_couleur_pb_intext_1 = fields.Char(string="Couleur PB (Int/Ext)")
    x_studio_cration_auto = fields.Boolean(string="Création Auto")
    x_studio_longueur_m = fields.Float(string="Longueur (m)")
    x_studio_longueur_pb_horizontal_1 = fields.Char(string="Longueur pb horizontal")
    x_studio_longueur_pb_vertical = fields.Char(string="longueur pb vertical")
    x_studio_nbr_pb_horizontal = fields.Integer(string="Nbr PB Horizontal")
    x_studio_nbr_pb_vertical = fields.Integer(string="Nbr PB Vertical")
    x_studio_position = fields.Char(string="Position")
    x_studio_position_en_x_pb_horizontal_1 = fields.Char(string="Position PB Horizontal (StartX/EndX)")
    x_studio_position_en_x_pb_vertical_1 = fields.Char(string="Position PB Vertical (StartX/EndX)")
    x_studio_position_en_y_pb_horizontal_1 = fields.Char(string="Position PB Horizontal (StartY/EndY)")
    x_studio_position_en_y_pb_vertical_1 = fields.Char(string="Position PB Vertical (StartY/EndY)")
    x_studio_ref_diapason = fields.Char(string="Ref Diapason")
    x_studio_ref_int_logikal = fields.Char(string="Ref Int Logikal")
    x_studio_spacer = fields.Char(string="spacer")
    x_studio_type = fields.Char(string="type")
    x_studio_type_pb = fields.Char(string="Type PB")
    x_studio_unit_logikal = fields.Char(string="Unité Logikal")


class ProductTemplate(models.Model):
    _inherit = "product.template"

    x_studio_conso_laffaire = fields.Boolean(string="Conso à l'affaire?", readonly=True)
    x_studio_entrept = fields.Char(string="Entrepôt")
    x_studio_hauteur_mm = fields.Integer(string="Hauteur (mm)")
    x_studio_largeur_mm = fields.Integer(string="Largeur (mm)")
