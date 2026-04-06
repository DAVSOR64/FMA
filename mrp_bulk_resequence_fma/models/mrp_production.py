# -*- coding: utf-8 -*-
import logging
import unicodedata

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    # Ordre voulu par l'utilisateur
    FMA_OPERATION_ORDER = [
        'Débit FMA',
        'CU (Banc) FMA',
        'Usinage FMA',
        'Montage FMA',
        'Vitrage FMA',
        'Emballage FMA',
    ]

    def _normalize_fma_name(self, name):
        name = (name or '').strip().casefold()
        # enlève les accents pour éviter Débit/debit et Banc/banc
        name = ''.join(c for c in unicodedata.normalize('NFKD', name) if not unicodedata.combining(c))
        # uniformise les espaces
        return ' '.join(name.split())

    def _fma_order_map(self):
        return {
            self._normalize_fma_name(label): (idx + 1) * 10
            for idx, label in enumerate(self.FMA_OPERATION_ORDER)
        }

    def _is_not_started_for_resequence(self):
        self.ensure_one()
        if self.state in ('done', 'cancel'):
            return False
        for wo in self.workorder_ids:
            if wo.state in ('progress', 'done', 'cancel'):
                return False
            if getattr(wo, 'date_start', False):
                return False
            if getattr(wo, 'qty_produced', 0):
                return False
        return True

    def _get_target_sequence_for_workorder(self, workorder):
        wc_name = workorder.workcenter_id.display_name or workorder.workcenter_id.name or ''
        return self._fma_order_map().get(self._normalize_fma_name(wc_name))

    def _apply_fma_operation_order(self):
        """Écrit la vraie séquence utilisée par le moteur de replanification.

        Important: le moteur mrp_replan_workorder trie sur wo.operation_id.sequence.
        Il faut donc persister cet ordre au niveau operation_id (et wo.sequence si le champ existe).
        """
        self.ensure_one()
        changed = False
        missing = []

        for wo in self.workorder_ids.filtered(lambda w: w.state not in ('done', 'cancel')):
            target_seq = self._get_target_sequence_for_workorder(wo)
            if not target_seq:
                continue

            wrote = False
            operation = getattr(wo, 'operation_id', False)
            if operation and 'sequence' in operation._fields:
                if operation.sequence != target_seq:
                    operation.with_context(mail_notrack=True).write({'sequence': target_seq})
                    changed = True
                wrote = True

            if 'sequence' in wo._fields and wo.sequence != target_seq:
                wo.with_context(mail_notrack=True, skip_shift_chain=True, skip_macro_recalc=True).write({'sequence': target_seq})
                changed = True
                wrote = True

            if not wrote:
                missing.append(wo.display_name or wo.name)

        return changed, missing

    def _get_fixed_end_dt_for_local_replan(self):
        self.ensure_one()
        return (
            getattr(self, 'macro_forced_end', False)
            or getattr(self, 'date_deadline', False)
            or getattr(self, 'date_finished', False)
            or getattr(self, 'date_planned_finished', False)
        )

    def _run_local_replan_with_existing_engine(self):
        """Appelle le vrai moteur existant, sans recalcul global."""
        self.ensure_one()
        if not hasattr(self, '_recalculate_macro_backward'):
            raise UserError(_("Le moteur de replanification local n'est pas disponible sur cette base."))

        workorders = self.workorder_ids.filtered(lambda w: w.state not in ('done', 'cancel'))
        if not workorders:
            return False

        fixed_end_dt = self._get_fixed_end_dt_for_local_replan()
        if not fixed_end_dt:
            raise UserError(_("Aucune date de fin n'est définie sur l'OF %s.") % (self.display_name or self.name))

        # Synchroniser les durées comme le popup standard
        for wo in workorders:
            if 'duration_expected' in wo._fields and 'duration' in wo._fields and wo.duration:
                if wo.duration_expected != wo.duration:
                    wo.duration_expected = wo.duration

        ctx = self.with_context(skip_macro_recalc=True, mail_notrack=True)
        ctx._recalculate_macro_backward(workorders, end_dt=fixed_end_dt)
        ctx.apply_macro_to_workorders_dates()
        ctx._update_mo_dates_from_macro(forced_end_dt=fixed_end_dt)
        ctx._update_components_picking_dates()
        if hasattr(ctx, '_refresh_charge_cache_for_production'):
            ctx._refresh_charge_cache_for_production()
        return True

    def action_resequence_fma(self):
        processed = self.browse()
        skipped = self.browse()
        missing_details = []

        for production in self:
            if not production._is_not_started_for_resequence():
                skipped |= production
                continue

            changed, missing = production._apply_fma_operation_order()
            if missing:
                missing_details.append('%s: %s' % (production.display_name or production.name, ', '.join(missing)))

            # Toujours relancer le moteur local, même si tout était déjà dans le bon ordre,
            # afin de recalculer les dates avec la règle courante.
            production._run_local_replan_with_existing_engine()
            processed |= production

            _logger.info(
                'FMA resequence | MO=%s | changed=%s | active WOs=%s',
                production.name, changed, production.workorder_ids.filtered(lambda w: w.state not in ('done', 'cancel')).ids,
            )

        parts = []
        if processed:
            parts.append(_('%s OF réordonnés/replanifiés.') % len(processed))
        if skipped:
            parts.append(_('%s OF ignorés (déjà lancés, terminés ou annulés).') % len(skipped))
        if missing_details:
            parts.append(_('Certaines opérations n\'ont pas de séquence modifiable : %s') % ' | '.join(missing_details[:5]))
        if not parts:
            parts = [_('Aucun OF éligible.')]

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Réordonnancement FMA'),
                'message': ' '.join(parts),
                'type': 'success' if processed else 'warning',
                'sticky': False,
            }
        }

    @api.model
    def action_resequence_fma_from_context(self):
        active_ids = self.env.context.get('active_ids') or []
        if not active_ids:
            raise UserError(_('Aucun OF sélectionné.'))
        return self.browse(active_ids).action_resequence_fma()
