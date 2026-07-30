# -*- coding: utf-8 -*-
"""Champs migrés depuis Odoo Studio.
Noms techniques conservés à l'identique, aucune migration de données.
Les 6 champs related listés ci-dessous avaient été exclus du portage initial
sur l'hypothèse que store=false signifiait "pas de données côté Studio" — en
réalité store=false est normal pour un champ related simplement recalculé à
la lecture (miroir en direct du produit/de la commande), pas un signe
d'absence de données. Vérifié en base (cf. session du 2026-07-30) :
x_studio_hauteur_mm/_1, x_studio_largeur_mm/_1, x_studio_related_field_2ji_1ipjatleh,
x_studio_related_field_9m_1ipjarf8a sont bien des related actifs en prod.
"""
from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    x_studio_date_livraison_prvue = fields.Datetime(
        string="Date Livraison prévue", related="order_id.commitment_date", store=True, readonly=True
    )
    x_studio_many2many_field_w5Rtg = fields.Many2many("sale.order", string="Bon de commande")
    x_studio_many2one_field_COPwF = fields.Many2one("sale.order", string="Bon de commande")
    x_studio_position = fields.Char(
        string="Position", related="product_id.x_studio_position", store=True, readonly=True
    )
    # Dimensions vitrage : deux champs candidats par dimension (mêmes valeurs,
    # related vers le même champ produit). Seuls les "_1" sont consommés par
    # un gabarit (custom_sale_order/views/sales_order.xml) ; les autres sont
    # conservés à l'identique de la prod mais non exposés ailleurs pour l'instant.
    x_studio_hauteur_mm = fields.Integer(
        string="Hauteur (mm)", related="product_id.x_studio_hauteur_mm", store=False, readonly=True
    )
    x_studio_hauteur_mm_1 = fields.Integer(
        string="Hauteur (mm)", related="product_id.x_studio_hauteur_mm", store=False, readonly=True
    )
    x_studio_largeur_mm = fields.Integer(
        string="Largeur (mm)", related="product_id.x_studio_largeur_mm", store=False, readonly=True
    )
    x_studio_largeur_mm_1 = fields.Integer(
        string="Largeur (mm)", related="product_id.x_studio_largeur_mm", store=False, readonly=True
    )
    x_studio_related_field_2ji_1ipjatleh = fields.Datetime(
        string="Nouveau Champ associé",
        related="x_studio_many2one_field_COPwF.expected_date",
        store=False,
        readonly=True,
    )
    x_studio_related_field_9m_1ipjarf8a = fields.Datetime(
        string="Nouveau Champ associé",
        related="x_studio_many2one_field_COPwF.commitment_date",
        store=True,
        readonly=True,
    )
