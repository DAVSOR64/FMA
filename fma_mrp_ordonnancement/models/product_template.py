# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    fma_exclu_reperes = fields.Boolean(
        string="Exclu du comptage des repères",
        help="Coché sur l'éco-participation et sur toute ligne de devis qui ne "
             "correspond pas à une menuiserie, afin qu'elle ne soit pas comptée "
             "dans le nombre de repères de l'ordre de fabrication.",
    )
