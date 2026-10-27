import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

#: Champs dont le changement modifie les heures ou le cout MOD d'une commande.
CHAMPS_MOD = {"duration", "date_start", "date_end", "employee_id", "user_id", "workorder_id"}


class MrpWorkcenterProductivity(models.Model):
    """Recalcule la MOD des commandes a chaque pointage.

    L'atelier cree un pointage au demarrage d'un ordre de travail et le
    complete a l'arret : c'est l'evenement qui fait bouger les heures reelles.
    La commande est recalculee a ce moment-la, et seulement celle-la.

    Encadre : une erreur dans ce calcul ne doit JAMAIS empecher un operateur
    de demarrer ou d'arreter un ordre de travail. Le pointage passe, l'erreur
    est journalisee.
    """

    _inherit = "mrp.workcenter.productivity"

    def _fma_commandes_concernees(self):
        commandes = self.env["sale.order"]
        for pointage in self:
            production = pointage.workorder_id.production_id
            if not production:
                continue
            commande = production._fma_commande_de_la_vente()
            if not commande and "lot_sale_order_id" in production._fields:
                commande = production.lot_sale_order_id
            if not commande and production.origin:
                commande = self.env["sale.order"].search(
                    [("name", "=", production.origin)], limit=1)
            commandes |= commande
        return commandes

    def _fma_recalculer_mod_commandes(self, commandes):
        if not commandes:
            return
        try:
            commandes._fma_recalculer_mod()
        except Exception:
            _logger.exception(
                "MOD reelle non recalculee pour %s", ", ".join(commandes.mapped("name")))

    @api.model_create_multi
    def create(self, vals_list):
        pointages = super().create(vals_list)
        try:
            commandes = pointages._fma_commandes_concernees()
        except Exception:
            _logger.exception("Commandes des pointages introuvables")
            return pointages
        self._fma_recalculer_mod_commandes(commandes)
        return pointages

    def write(self, vals):
        if not CHAMPS_MOD.intersection(vals):
            return super().write(vals)
        # Avant ET apres : un pointage deplace d'un ordre de travail a un autre
        # change deux commandes.
        try:
            avant = self._fma_commandes_concernees()
        except Exception:
            avant = self.env["sale.order"]
        res = super().write(vals)
        try:
            apres = self._fma_commandes_concernees()
        except Exception:
            apres = self.env["sale.order"]
        self._fma_recalculer_mod_commandes(avant | apres)
        return res

    def unlink(self):
        try:
            commandes = self._fma_commandes_concernees()
        except Exception:
            commandes = self.env["sale.order"]
        res = super().unlink()
        self._fma_recalculer_mod_commandes(commandes.exists())
        return res
