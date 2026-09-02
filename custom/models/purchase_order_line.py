# -*- coding: utf-8 -*-
"""Champs migrés depuis Odoo Studio.
Noms techniques conservés à l'identique, aucune migration de données.
"""
from odoo import api, fields, models


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    # Ces 3 champs sont aussi des related vers le produit en prod (mêmes
    # vérifications que Hauteur/Largeur ci-dessous), mais stockés (store=true)
    # côté ir_model_fields, contrairement à Hauteur/Largeur.
    x_studio_forme = fields.Char(string="Forme", related="product_id.x_studio_type", store=True, readonly=True)
    x_studio_posit = fields.Char(string="Position/N°")

    # Repere affiche : MEME regle que le PDF d'achat, qui prend x_studio_posit
    # quand il est renseigne et retombe sinon sur x_studio_position, le related
    # vers le produit (custom_purchase_documents/views/custom_invoice_filling.xml).
    # Le formulaire, lui, n'affichait que le premier : la colonne restait vide
    # alors que le PDF, sorti des memes lignes, portait bien un repere.
    x_fma_repere = fields.Char(
        string="Repère", compute="_compute_x_fma_repere", readonly=True)

    @api.depends("x_studio_posit", "x_studio_position")
    def _compute_x_fma_repere(self):
        for ligne in self:
            ligne.x_fma_repere = ligne.x_studio_posit or ligne.x_studio_position or False
    x_studio_position = fields.Char(
        string="position", related="product_id.x_studio_position", store=True, readonly=True
    )
    x_studio_spacer = fields.Char(string="spacer")
    x_studio_spacer_2 = fields.Char(
        string="Spacer", related="product_id.x_studio_spacer", store=True, readonly=True
    )
    # Dimensions vitrage : related vers le produit en prod (confirmé en base :
    # ir_model_fields.related='product_id.x_studio_hauteur_mm'/'largeur_mm',
    # store=false), pas des valeurs saisies/stockées sur la ligne. Une
    # première tentative de portage les avait déclarés en Integer stockés
    # indépendants, ce qui cassait le lien avec le produit (valeurs à 0).
    x_studio_hauteur = fields.Integer(
        string="Hauteur", related="product_id.x_studio_hauteur_mm", store=False, readonly=True
    )
    x_studio_largeur = fields.Integer(
        string="Largeur", related="product_id.x_studio_largeur_mm", store=False, readonly=True
    )
