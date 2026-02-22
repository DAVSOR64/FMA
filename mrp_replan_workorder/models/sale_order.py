# -*- coding: utf-8 -*-
import logging
from datetime import timedelta
from odoo import models, fields

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        """
        Déclenche la planification automatique des OF après confirmation du devis.
        La planification se fait depuis la date promise (SO.commitment_date),
        sans écrire de champ sur l'OF.
        """
        for order in self:
            _logger.info("=== Validation commande %s ===", order.name)

        res = super().action_confirm()

        for order in self:
            # 1) Déterminer une date "cible" de livraison
            # Priorité: commitment_date du SO (vraie promesse)
            commitment_dt = order.commitment_date

            # Fallback: si pas de commitment_date, construire une date via délai max des lignes
            if not commitment_dt:
                leads = order.order_line.mapped('customer_lead')
                lead_days = int(max(leads)) if leads else 0
                commitment_dt = fields.Datetime.to_datetime(order.date_order) + timedelta(days=lead_days)
                _logger.info("SO %s sans commitment_date -> fallback (date_order + %s j) = %s",
                             order.name, lead_days, commitment_dt)

            # 2) Récupérer les OF liés à la commande
            # Méthode plus robuste que origin=self.name : procurement_group_id
            productions = self.env['mrp.production'].search([
                ('procurement_group_id', '=', order.procurement_group_id.id),
                ('state', 'in', ['draft', 'confirmed']),
            ])

            if not productions:
                # fallback si ton flux ne renseigne pas procurement_group_id
                productions = self.env['mrp.production'].search([
                    ('origin', '=', order.name),
                    ('state', 'in', ['draft', 'confirmed']),
                ])

            if not productions:
                _logger.info("Commande %s : aucun OF trouvé", order.name)
                continue

            _logger.info("Commande %s : %d OF(s) trouvé(s), lancement planification",
                         order.name, len(productions))

            for mo in productions:
                try:
                    mo.compute_macro_schedule_from_sale(order, security_days=6)
                    _logger.info("OF %s planifié avec succès", mo.name)
                except Exception as e:
                    _logger.exception("Erreur planification OF %s : %s", mo.name, str(e))

        return res
