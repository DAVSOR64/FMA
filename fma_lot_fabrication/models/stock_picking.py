# -*- coding: utf-8 -*-
"""Terminaison automatique des OF de quincaillerie.

L'OF de quincaillerie n'a pas d'operation : le travail qu'il represente est la
sortie de la quincaillerie du stock vers la Pre-Fab, et ce transfert existe
deja. L'OF se termine donc seul, a l'arrivee de ses composants.

Le critere n'est PAS « tel transfert a ete valide ». Le magasin sort souvent
tout ensemble — profiles, vitrages, quincaillerie — ou en plusieurs fois, les
profiles d'abord. Un OF de quincaillerie ne se termine que lorsque SES
composants, et eux seuls, sont tous disponibles en Pre-Fab. Sortir les
profiles d'abord ne le touche pas ; il se termine quand la derniere piece de
quincaillerie arrive, dans le transfert d'origine ou dans son reliquat.
"""
import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    # LE LOT SUR LE TRANSFERT, et stocke. Le magasin prepare a la journee :
    # il lui faut une liste des sorties du jour avec, en face de chacune,
    # l'affaire et le lot. Le lot connaissait ses transferts — par un calcul
    # non stocke, donc ni groupable ni cherchable ; le transfert, lui, ne
    # connaissait pas son lot. C'est le lot qui l'ecrit en regroupant ses
    # sorties : lui seul sait lesquelles lui appartiennent.
    lot_fabrication_id = fields.Many2one(
        "fma.lot.fabrication",
        string="Lot de fabrication",
        index="btree_not_null",
        ondelete="set null",
        copy=False,
    )
    # La commande du lot, pour grouper la preparation par affaire sans
    # ouvrir le lot. Related STOCKE : un related simple ne se grouperait pas.
    lot_commande_id = fields.Many2one(
        "sale.order",
        string="Commande",
        related="lot_fabrication_id.ordo_commande_id",
        store=True,
        index="btree_not_null",
    )

    def action_imprimer_besoin_matiere_lot(self):
        """Le besoin matiere du lot, depuis le transfert.

        Le rapport est rattache au LOT, et le magasin arrive par le
        transfert : sans ce bouton il faut ouvrir le lot pour l'imprimer,
        et le menu « Imprimer » du transfert ne le propose pas puisqu'il
        n'y est pas rattache.
        """
        self.ensure_one()
        if not self.lot_fabrication_id:
            raise UserError(_(
                "Ce transfert n'appartient à aucun lot de fabrication : il "
                "n'y a pas de besoin matière à imprimer."))
        return self.lot_fabrication_id.action_imprimer_besoin_matiere()

    def _action_done(self):
        res = super()._action_done()
        # Encadre : terminer un kit est un confort. Une erreur ici ne doit
        # jamais empecher de valider un transfert — le magasin serait bloque
        # pour un OF que personne ne pointe.
        try:
            self._fma_terminer_kits_quincaillerie()
        except Exception:  # noqa: BLE001
            _logger.exception(
                "Kits de quincaillerie non termines apres validation de %s",
                ", ".join(self.mapped("name")),
            )
        return res

    def _fma_terminer_kits_quincaillerie(self):
        """Termine les OF de quincaillerie dont toute la matiere est arrivee."""
        Move = self.env["stock.move"]
        if "raw_material_production_id" not in Move._fields:
            return

        # Les mouvements du transfert alimentent ceux de l'OF : le lien passe
        # par le chainage, pas par le transfert lui-meme.
        aval = self.move_ids.move_dest_ids
        kits = aval.raw_material_production_id.filtered(
            lambda p: p.lot_production_type == "quincaillerie"
            and p.state in ("confirmed", "progress", "to_close")
        )
        for kit in kits:
            kit.action_assign()
            if kit.reservation_state != "assigned":
                # Toute la quincaillerie n'est pas la : on attend. Un kit
                # termine partiellement creerait un reliquat, pour rien.
                continue
            kit._fma_terminer_sans_intervention()


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def _fma_terminer_sans_intervention(self):
        """Declare l'OF entierement produit, sans assistant ni reliquat."""
        self.ensure_one()
        self.qty_producing = self.product_qty
        if hasattr(self, "_set_qty_producing"):
            self._set_qty_producing()
        resultat = self.with_context(
            skip_backorder=True,
            skip_immediate=True,
            skip_consumption=True,
        ).button_mark_done()

        if self.state != "done":
            # button_mark_done renvoie un assistant quand quelque chose
            # l'arrete — ecart de consommation, numero de serie manquant. On ne
            # force pas : on le dit sur l'OF, ou quelqu'un le verra.
            _logger.warning(
                "Kit %s non termine automatiquement : %s", self.name, resultat
            )
            self.message_post(
                body=_(
                    "Toute la quincaillerie est arrivee en Pre-Fab, mais cet OF "
                    "n'a pas pu etre termine automatiquement. A terminer a la "
                    "main."
                )
            )
