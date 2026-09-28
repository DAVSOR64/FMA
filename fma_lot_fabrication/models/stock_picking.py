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

from odoo import _, models

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

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
