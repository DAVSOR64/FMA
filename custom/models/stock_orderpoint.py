# -*- coding: utf-8 -*-
from odoo import models, fields
from odoo.tools import float_round


class StockWarehouseOrderpoint(models.Model):
    """Retablit le multiple numerique des regles de reapprovisionnement.

    Odoo 19 a supprime qty_multiple et l'a remplace par replenishment_uom_id,
    une unite de mesure : le multiple ne s'exprime plus par un nombre mais par
    une unite qui le porte (« Boite de 25 », « Barre de 6 m »). Le domaine du
    champ n'accepte que les unites declarees sur le produit ou celles du
    fournisseur.

    Le raisonnement se defend pour un catalogue de conditionnements ; il ne
    tient pas ici. FMA a des centaines de references dont le multiple d'achat
    est propre a chacune, et creer une unite de mesure par reference pour
    exprimer un simple nombre est ingerable.

    Ce champ redonne donc la saisie directe, sans rien retirer du mecanisme
    natif : les deux se composent. L'unite de reapprovisionnement arrondit
    d'abord si elle est renseignee, le multiple numerique arrondit ensuite.
    """

    _inherit = "stock.warehouse.orderpoint"

    fma_qty_multiple = fields.Float(
        string="Multiple (quantité)",
        digits="Product Unit of Measure",
        default=0.0,
        help="Les quantités à commander sont arrondies au multiple supérieur "
             "de cette valeur, exprimée dans l'unité du produit. Laisser à "
             "zéro pour ne pas arrondir.",
    )

    def _get_multiple_rounded_qty(self, qty_to_order):
        """Arrondit au multiple superieur, apres l'arrondi natif.

        super() applique d'abord replenishment_uom_id quand elle est
        renseignee — on ne lui retire rien. Le multiple numerique s'applique
        ensuite, et un zero laisse la quantite intacte.
        """
        qty_to_order = super()._get_multiple_rounded_qty(qty_to_order)

        multiple = self.fma_qty_multiple
        if multiple <= 0 or qty_to_order <= 0:
            return qty_to_order

        # L'arrondi de l'unite du produit, pour ne pas reintroduire les
        # decimales que la division fait apparaitre (7 / 0.1 = 69.999...).
        arrondi = self.product_id.uom_id.rounding or 0.01
        lots = float_round(
            qty_to_order / multiple, precision_digits=0, rounding_method="UP")
        return float_round(lots * multiple, precision_rounding=arrondi)
