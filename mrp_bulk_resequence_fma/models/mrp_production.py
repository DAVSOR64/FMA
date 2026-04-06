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
            if getattr(wo, 'date_start', False):
                return False
            if getattr(wo, 'qty_produced', 0):
                return False
        return True

    def _get_current_workorder_order(self, workorder):
        operation = getattr(workorder, 'operation_id', False)
        if operation and 'sequence' in operation._fields:
            return operation.sequence or 0
        return 0

    def _get_fma_workorder_rank(self, workorder):
        wc_name = (workorder.workcenter_id.name or '').strip()
        try:
            return self.FMA_OPERATION_ORDER.index(wc_name)
        except ValueError:
            return len(self.FMA_OPERATION_ORDER) + (self._get_current_workorder_order(workorder) / 1000.0)

    def _get_fma_ordered_workorders(self):
        self.ensure_one()
        return self.workorder_ids.sorted(
            key=lambda wo: (
                self._get_fma_workorder_rank(wo),
                self._get_current_workorder_order(wo),
                wo.id,
            )
        )

    def _get_local_replan_start(self):
        self.ensure_one()
        for fname in ('date_planned_start', 'date_start', 'date_deadline', 'create_date'):
            if fname in self._fields:
                value = self[fname]
                if value:
                    return value
        return fields.Datetime.now()

    def _duration_delta_for_workorder(self, workorder):
        minutes = getattr(workorder, 'duration_expected', 0.0) or 0.0
        if minutes < 0:
            minutes = 0.0
        return timedelta(minutes=minutes)

    def _write_workorder_dates(self, workorder, start_dt, end_dt):
        vals = {}
        if 'date_start' in workorder._fields:
            vals['date_start'] = start_dt
        if 'date_finished' in workorder._fields:
            vals['date_finished'] = end_dt
        elif 'date_end' in workorder._fields:
            vals['date_end'] = end_dt
        if vals:
            workorder.write(vals)

    def _write_production_dates(self, production, first_start, last_end):
        vals = {}
        for start_name in ('date_planned_start', 'date_start'):
            if start_name in production._fields:
                vals[start_name] = first_start
                break
        for end_name in ('date_deadline', 'date_finished', 'date_end'):
            if end_name in production._fields:
                vals[end_name] = last_end
                break
        if vals:
            production.write(vals)

    def _resequence_operation_sequences_if_possible(self):
        """Optionnel: recale les séquences des opérations liées quand le champ existe."""
        for production in self:
            ordered_wos = production._get_fma_ordered_workorders()
            seq = 10
            for wo in ordered_wos:
                operation = getattr(wo, 'operation_id', False)
                if operation and 'sequence' in operation._fields:
                    operation.sequence = seq
                    seq += 10

    def _replan_workorders_locally(self):
        for production in self:
            current_dt = production._get_local_replan_start()
            workorders = production._get_fma_ordered_workorders()
            if not workorders:
                continue

            for wo in workorders:
                delta = production._duration_delta_for_workorder(wo)
                end_dt = current_dt + delta
                production._write_workorder_dates(wo, current_dt, end_dt)
                current_dt = end_dt

            production._write_production_dates(production, workorders[0].date_start or production._get_local_replan_start(), current_dt)

    def action_resequence_fma(self):
        skipped = self.browse()
        processed = self.browse()

        for production in self:
            if production._is_not_started_for_resequence():
                production._resequence_operation_sequences_if_possible()
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
