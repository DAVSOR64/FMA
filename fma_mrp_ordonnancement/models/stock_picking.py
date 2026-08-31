# -*- coding: utf-8 -*-
from odoo import models


class StockPicking(models.Model):
    """Déclencheur de recalcul à la validation d'une réception.

    Le statut de réception d'une commande d'achat bascule au moment où le
    transfert est validé, sans aucune écriture sur l'OF : sans ce déclencheur,
    les colonnes « Réception … » resteraient sur leur valeur précédente.
    """

    _inherit = 'stock.picking'

    def _fma_commandes_achat(self):
        """Commandes d'achat portées par ces transferts, si purchase_stock."""
        commandes = self.env['purchase.order']
        if 'purchase_id' in self._fields:
            commandes |= self.mapped('purchase_id')
        return commandes

    def _fma_invalider_appro(self):
        commandes = self._fma_commandes_achat()
        if commandes:
            commandes._fma_invalider_appro()

    def button_validate(self):
        result = super().button_validate()
        self._fma_invalider_appro()
        return result

    def action_cancel(self):
        result = super().action_cancel()
        self._fma_invalider_appro()
        return result
