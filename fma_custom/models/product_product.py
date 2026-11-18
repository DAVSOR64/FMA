# -*- coding: utf-8 -*-
"""Ce qu'un article doit dire de lui-meme a la validation d'un devis."""
from odoo import models


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _fma_achete_sur_commande(self):
        """L'article declenche-t-il un ACHAT quand on en a besoin ?

        Le critere est la ROUTE, et non « peut etre achete » : ce dernier dit
        seulement qu'un acheteur a le droit de le commander a la main, pas
        qu'Odoo lancera un bon tout seul. Un article de stock reapprovisionne
        par point de commande, ou fabrique, n'a pas a porter de fournisseur
        pour qu'un devis soit validable.

        On cherche donc une regle « Acheter » dans ses routes, ou dans celles
        de sa categorie — Odoo lit les deux.
        """
        self.ensure_one()
        routes = self.route_ids | self.categ_id.total_route_ids if (
            "total_route_ids" in self.categ_id._fields) else self.route_ids
        return any(
            regle.action == "buy"
            for route in routes
            for regle in route.rule_ids
        )
