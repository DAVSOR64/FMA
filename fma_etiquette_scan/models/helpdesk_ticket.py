# -*- coding: utf-8 -*-
"""Le ticket SAV rattache a UNE menuiserie.

helpdesk_stock porterait un champ lot_id, mais il n'est pas installe chez
FMA et tire la gestion des retours avec lui. Le lien est donc porte ici,
sur un champ propre ; l'ordre, le lot et la commande en decoulent.
"""
from odoo import api, fields, models


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    fma_serial_id = fields.Many2one(
        "stock.lot",
        string="Menuiserie (n° de série)",
        index="btree_not_null",
        ondelete="restrict",
        tracking=True,
        help="La menuiserie concernee, designee par le numero de serie de "
        "son etiquette.",
    )
    fma_product_id = fields.Many2one(
        related="fma_serial_id.product_id", string="Article", store=True)
    fma_production_id = fields.Many2one(
        "mrp.production", string="Ordre de fabrication",
        compute="_compute_fma_origine", store=True)
    fma_lot_fabrication_id = fields.Many2one(
        "fma.lot.fabrication", string="Lot de fabrication",
        compute="_compute_fma_origine", store=True)
    fma_sale_order_id = fields.Many2one(
        "sale.order", string="Commande",
        compute="_compute_fma_origine", store=True)
    fma_affaire = fields.Char(related="fma_serial_id.fma_affaire")
    fma_chantier = fields.Char(related="fma_serial_id.fma_chantier")
    fma_repere = fields.Char(related="fma_serial_id.fma_repere")
    fma_livraison = fields.Char(related="fma_serial_id.fma_livraison")
    fma_date_fabrication = fields.Datetime(
        related="fma_serial_id.fma_date_fabrication")

    @api.depends("fma_serial_id")
    def _compute_fma_origine(self):
        """Fige a la saisie du numero : le ticket garde la trace de l'ordre
        et du lot meme si la menuiserie est refabriquee ensuite."""
        for ticket in self:
            serie = ticket.fma_serial_id
            if not serie:
                ticket.fma_production_id = False
                ticket.fma_lot_fabrication_id = False
                ticket.fma_sale_order_id = False
                continue
            ctx = serie._fma_contexte()
            ticket.fma_production_id = ctx["ordre"]
            ticket.fma_lot_fabrication_id = ctx["lot"]
            ticket.fma_sale_order_id = ctx["commande"]

    def _fma_ouvrir(self, enregistrement):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": enregistrement._name,
            "res_id": enregistrement.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_fma_voir_serie(self):
        return self._fma_ouvrir(self.fma_serial_id)

    def action_fma_voir_of(self):
        return self._fma_ouvrir(self.fma_production_id)

    def action_fma_voir_lot(self):
        return self._fma_ouvrir(self.fma_lot_fabrication_id)

    def action_fma_voir_commande(self):
        return self._fma_ouvrir(self.fma_sale_order_id)
