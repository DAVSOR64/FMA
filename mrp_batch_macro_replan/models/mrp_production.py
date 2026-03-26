# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    def _is_macro_batch_eligible(self):
        """
        OF éligible au recalcul batch :
        - état confirmé / en cours
        - au moins un OT actif
        - aucun OT réellement démarré
        """
        self.ensure_one()

        active_wos = self.workorder_ids.filtered(lambda w: w.state not in ('done', 'cancel'))
        if not active_wos:
            return False

        # On considère qu'un OT est démarré s'il est en cours, terminé,
        # ou s'il possède déjà un vrai début d'exécution / temps saisi.
        started_wos = active_wos.filtered(
            lambda w: w.state == 'progress'
            or bool(w.date_start)
            or bool(w.duration)
            or bool(w.qty_produced)
        )
        return not bool(started_wos)

    def _get_macro_target_date(self):
        """Retourne la date cible pour le recalcul macro."""
        self.ensure_one()

        sale_order = False
        if self.procurement_group_id:
            sale_order = self.env['sale.order'].search([
                ('procurement_group_id', '=', self.procurement_group_id.id)
            ], limit=1)

        delivery_dt = False
        if sale_order and sale_order.commitment_date:
            delivery_dt = fields.Datetime.to_datetime(sale_order.commitment_date)

        if not delivery_dt and self.date_deadline:
            delivery_dt = fields.Datetime.to_datetime(self.date_deadline)
        if not delivery_dt and self.date_finished:
            delivery_dt = fields.Datetime.to_datetime(self.date_finished)
        if not delivery_dt and getattr(self, 'macro_forced_end', False):
            delivery_dt = fields.Datetime.to_datetime(self.macro_forced_end)

        return delivery_dt, sale_order

    def _recompute_single_macro_planning(self, security_days=6):
        self.ensure_one()

        delivery_dt, sale_order = self._get_macro_target_date()
        if not delivery_dt:
            raise ValueError(_('Aucune date cible trouvée pour l\'OF %s.') % self.display_name)

        # Utilise la logique standard existante du module mrp_replan_workorder.
        if sale_order and sale_order.commitment_date:
            self.compute_macro_schedule_from_sale(sale_order, security_days=security_days)
        else:
            # Objet léger compatible avec compute_macro_schedule_from_sale
            dummy_sale = self.env['sale.order'].new({'commitment_date': delivery_dt})
            self.compute_macro_schedule_from_sale(dummy_sale, security_days=security_days)

        return True

    @api.model
    def action_batch_recompute_macro_not_started(self, security_days=6, limit=None):
        domain = [('state', 'in', ['confirmed', 'progress'])]
        mos = self.search(domain, order='priority desc, date_deadline asc, id asc', limit=limit)

        treated = 0
        skipped_started = 0
        skipped_no_target = 0
        errors = []

        for mo in mos:
            try:
                if not mo._is_macro_batch_eligible():
                    skipped_started += 1
                    continue

                delivery_dt, _sale = mo._get_macro_target_date()
                if not delivery_dt:
                    skipped_no_target += 1
                    _logger.warning('Replan macro batch ignoré pour %s : aucune date cible', mo.display_name)
                    continue

                mo._recompute_single_macro_planning(security_days=security_days)
                treated += 1
            except Exception as exc:
                errors.append('%s : %s' % (mo.display_name, exc))
                _logger.exception('Erreur recalcul macro batch sur %s', mo.display_name)

        if 'mrp.capacite.cache' in self.env:
            self.env['mrp.capacite.cache'].refresh()
        if 'mrp.workorder.charge.cache' in self.env:
            self.env['mrp.workorder.charge.cache'].refresh()

        message_parts = [
            _('%s OF recalculé(s)') % treated,
            _('%s OF ignoré(s) car déjà démarré(s)') % skipped_started,
            _('%s OF ignoré(s) sans date cible') % skipped_no_target,
        ]
        if errors:
            message_parts.append(_('%s erreur(s)') % len(errors))

        return {
            'treated': treated,
            'skipped_started': skipped_started,
            'skipped_no_target': skipped_no_target,
            'errors': errors,
            'message': ' | '.join(message_parts),
        }
