from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    FMA_OPERATION_ORDER = [
        'Débit FMA',
        'CU (Banc) FMA',
        'Usinage FMA',
        'Montage FMA',
        'Vitrage FMA',
        'Emballage FMA',
    ]

    def _is_not_started_for_resequence(self):
        self.ensure_one()
        if self.state in ('done', 'cancel'):
            return False
        started_states = {'progress', 'done', 'cancel'}
        for wo in self.workorder_ids:
            if wo.state in started_states:
                return False
            if wo.date_start:
                return False
            if getattr(wo, 'qty_produced', 0):
                return False
        return True

    def _get_fma_workorder_rank(self, workorder):
        wc_name = (workorder.workcenter_id.name or '').strip()
        try:
            return self.FMA_OPERATION_ORDER.index(wc_name)
        except ValueError:
            return len(self.FMA_OPERATION_ORDER) + ((workorder.sequence or 0) / 1000.0)

    def _apply_fma_operation_order(self):
        for production in self:
            ordered_wos = production.workorder_ids.sorted(
                key=lambda wo: (production._get_fma_workorder_rank(wo), wo.sequence or 0, wo.id)
            )
            seq = 10
            for wo in ordered_wos:
                wo.sequence = seq
                seq += 10

    def _get_local_replan_start(self):
        self.ensure_one()
        return (
            self.date_planned_start
            or self.date_start
            or fields.Datetime.now()
        )

    def _duration_delta_for_workorder(self, workorder):
        minutes = workorder.duration_expected or 0.0
        if minutes < 0:
            minutes = 0.0
        return timedelta(minutes=minutes)

    def _replan_workorders_locally(self):
        """Replanifie uniquement les OT de l'OF courant, sans recalcul global."""
        for production in self:
            current_dt = production._get_local_replan_start()
            workorders = production.workorder_ids.sorted(lambda wo: (wo.sequence or 0, wo.id))
            if not workorders:
                continue

            for wo in workorders:
                delta = production._duration_delta_for_workorder(wo)
                wo.write({
                    'date_start': current_dt,
                    'date_finished': current_dt + delta,
                })
                current_dt = current_dt + delta

            production.write({
                'date_planned_start': workorders[0].date_start,
                'date_deadline': workorders[-1].date_finished,
            })

    def action_resequence_fma(self):
        skipped = self.browse()
        processed = self.browse()

        for production in self:
            if production._is_not_started_for_resequence():
                production._apply_fma_operation_order()
                production._replan_workorders_locally()
                processed |= production
            else:
                skipped |= production

        message_parts = []
        if processed:
            message_parts.append(_('%s OF réordonnés et replanifiés.') % len(processed))
        if skipped:
            message_parts.append(_('%s OF ignorés (déjà lancés, terminés ou annulés).') % len(skipped))
        if not message_parts:
            message_parts.append(_('Aucun OF éligible.'))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Réordonnancement FMA'),
                'message': ' '.join(message_parts),
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
