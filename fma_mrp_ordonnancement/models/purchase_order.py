# -*- coding: utf-8 -*-
import logging

from odoo import api, models

from .constants import FMA_ETATS_CLOS

_logger = logging.getLogger(__name__)

# Champs dont la modification change une colonne d'approvisionnement de l'OF.
CHAMPS_DECLENCHEURS = {
    'state',
    'partner_id',
    'origin',
    'date_planned',
    'x_studio_projet_du_so',
}


class PurchaseOrder(models.Model):
    """Déclencheurs de recalcul côté achat.

    Le lien OF <-> commande d'achat n'est pas un champ relationnel : il est
    résolu par algorithme dans mrp.production._fma_purchase_orders. Aucun
    chemin d'@api.depends ne peut donc atteindre l'OF, et sans ce qui suit les
    colonnes L à Q resteraient figées à leur valeur de création.
    """

    _inherit = 'purchase.order'

    def _fma_productions_liees(self):
        """Résolution inverse : de la commande d'achat vers les OF ouverts.

        On ne recalcule surtout pas tous les OF à chaque écriture : un OF coûte
        plusieurs recherches dans _compute_fma_appro. On cible donc, dans
        l'ordre, la chaîne d'approvisionnement, l'origine, puis le projet du
        SO — les trois voies par lesquelles _fma_purchase_orders retrouve la
        commande. Ce qui échapperait à ces trois voies est rattrapé par le cron.
        """
        Production = self.env['mrp.production']
        productions = Production

        # 1. Chaîne MTO : les mouvements générés par l'achat alimentent l'OF.
        Move = self.env['stock.move']
        for ligne in self.order_line:
            moves = Move
            if 'move_dest_ids' in ligne._fields:
                moves |= ligne.move_dest_ids
            if 'move_ids' in ligne._fields:
                moves |= ligne.move_ids.move_dest_ids
            if 'raw_material_production_id' in Move._fields:
                productions |= moves.raw_material_production_id
            if 'production_id' in Move._fields:
                productions |= moves.production_id

        # 2. Origine : l'achat cite le nom de l'OF.
        origines = [purchase.origin for purchase in self if purchase.origin]
        if origines:
            jetons = set()
            for origine in origines:
                for jeton in origine.replace(',', ' ').split():
                    if '/' in jeton:
                        jetons.add(jeton.strip())
            if jetons:
                productions |= Production.search([('name', 'in', list(jetons))])

        # 3. Projet du SO : achats saisis à la main, hors chaîne d'appro.
        if 'x_studio_projet_du_so' in self._fields:
            projets = self.mapped('x_studio_projet_du_so')
            if projets and 'x_studio_projet' in self.env['sale.order']._fields:
                commandes = self.env['sale.order'].search([
                    ('x_studio_projet', 'in', projets.ids),
                ])
                if commandes:
                    productions |= Production.search([
                        ('sale_line_id', 'in', commandes.order_line.ids),
                    ])

        return productions.filtered(lambda mo: mo.state not in FMA_ETATS_CLOS)

    def _fma_invalider_appro(self):
        productions = self._fma_productions_liees()
        if not productions:
            return
        self.env['mrp.production']._fma_marquer_recalcul(
            self.env['mrp.production']._fma_champs_appro(),
            productions=productions,
        )

    @api.model_create_multi
    def create(self, vals_list):
        commandes = super().create(vals_list)
        commandes._fma_invalider_appro()
        return commandes

    def write(self, vals):
        result = super().write(vals)
        if CHAMPS_DECLENCHEURS & set(vals):
            self._fma_invalider_appro()
        return result

    def button_confirm(self):
        result = super().button_confirm()
        self._fma_invalider_appro()
        return result

    def button_cancel(self):
        result = super().button_cancel()
        self._fma_invalider_appro()
        return result


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    def write(self, vals):
        result = super().write(vals)
        # La date d'arrivée prévue est portée par la ligne : c'est elle qui
        # alimente les colonnes « Arrivée … » de l'OF.
        if {'date_planned', 'product_qty', 'product_id'} & set(vals):
            self.order_id._fma_invalider_appro()
        return result
