# -*- coding: utf-8 -*-
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

# Valeur du champ « Rappels » du bloc Suivi des factures. Chez FMA la relance
# part a la main, depuis la liste des factures : personne ne doit recevoir un
# rappel qu'un humain n'a pas decide d'envoyer.
RAPPEL_MANUEL = "manual"


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model
    def default_get(self, fields_list):
        """Un nouveau client ne part pas en relance automatique.

        Odoo cree les clients en « Automatique ». Sans ce defaut, chaque fiche
        creee demain rouvrirait la porte que la bascule ci-dessous vient de
        fermer, et personne ne s'en apercevrait avant qu'un client recoive un
        rappel non voulu.
        """
        valeurs = super().default_get(fields_list)
        # Champ d'un module Enterprise : il peut ne pas etre installe.
        if "followup_reminder_type" in self._fields:
            valeurs.setdefault("followup_reminder_type", RAPPEL_MANUEL)
        return valeurs

    @api.model
    def action_fma_relances_en_manuel(self):
        """Bascule tous les clients en rappel manuel.

        A lancer une fois. Ne touche que ceux encore en automatique, pour que
        le journal dise exactement combien de fiches ont change — un write sur
        l'ensemble ne l'aurait pas dit.
        """
        if "followup_reminder_type" not in self._fields:
            _logger.warning(
                "Relance : le champ « followup_reminder_type » n'existe pas, "
                "account_followup n'est probablement pas installe."
            )
            return True
        clients = self.sudo().search([
            ("followup_reminder_type", "!=", RAPPEL_MANUEL),
        ])
        if not clients:
            _logger.info("Relance : tous les clients sont deja en rappel manuel.")
            return True
        clients.write({"followup_reminder_type": RAPPEL_MANUEL})
        _logger.info("Relance : %s client(s) bascule(s) en rappel manuel.", len(clients))
        return True
