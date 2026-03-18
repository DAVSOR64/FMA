
# -*- coding: utf-8 -*-
import json
import math
from datetime import datetime, timedelta, time
from odoo import _, fields, models
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    def action_open_replan_preview(self):
        self.ensure_one()
        payload = self._build_replan_preview()
        wizard = self.env['mrp.replan.preview.wizard'].create({
            'production_id': self.id,
            'summary_html': payload['summary_html'],
            'preview_json': json.dumps(payload['data'], default=str),
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Prévisualisation recalcul OF'),
            'res_model': 'mrp.replan.preview.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _build_replan_preview(self):
        self.ensure_one()
        workorders = self.workorder_ids.filtered(lambda w: w.state not in ('done', 'cancel')).sorted(
            lambda w: (w.operation_id.sequence if w.operation_id else 0, w.id)
        )
        if not workorders:
            raise UserError(_('Aucune opération active à recalculer.'))

        end_dt = self.date_deadline or self.date_finished
        start_dt = self.date_start
        strategy = 'backward' if end_dt else 'forward'
        preview_lines = []

        if strategy == 'backward':
            current_day = fields.Datetime.to_datetime(end_dt).date()
            current_day = self._previous_or_same_working_day(current_day, workorders[-1].workcenter_id)
            seq = list(workorders)[::-1]
            computed = []
            for wo in seq:
                wc = wo.workcenter_id
                cal = wc.resource_calendar_id or self.env.company.resource_calendar_id
                hours_per_day = (cal.hours_per_day or 7.8) if cal else 7.8
                effective_hours, nb_resources = self._get_effective_duration_hours(wo)
                required_days = max(1, int(math.ceil(effective_hours / hours_per_day)))
                last_day = self._previous_or_same_working_day(current_day, wc)
                first_day = last_day
                for _i in range(required_days - 1):
                    first_day = self._previous_working_day(first_day, wc)
                start_line = self._morning_dt(first_day, wc)
                end_line = self._evening_dt(last_day, wc)
                computed.append({
                    'wo_id': wo.id,
                    'name': wo.name,
                    'start': fields.Datetime.to_string(start_line),
                    'end': fields.Datetime.to_string(end_line),
                    'nb_resources': nb_resources,
                })
                current_day = self._previous_working_day(first_day, wc)
            preview_lines = list(reversed(computed))
        else:
            if not start_dt:
                start_dt = datetime.combine(fields.Date.today(), time(7, 30))
            current_day = fields.Datetime.to_datetime(start_dt).date()
            for wo in workorders:
                wc = wo.workcenter_id
                cal = wc.resource_calendar_id or self.env.company.resource_calendar_id
                hours_per_day = (cal.hours_per_day or 7.8) if cal else 7.8
                effective_hours, nb_resources = self._get_effective_duration_hours(wo)
                required_days = max(1, int(math.ceil(effective_hours / hours_per_day)))
                first_day = self._previous_or_same_working_day(current_day, wc)
                last_day = first_day
                for _i in range(required_days - 1):
                    last_day = self._next_working_day(last_day, wc)
                start_line = self._morning_dt(first_day, wc)
                end_line = self._evening_dt(last_day, wc)
                preview_lines.append({
                    'wo_id': wo.id,
                    'name': wo.name,
                    'start': fields.Datetime.to_string(start_line),
                    'end': fields.Datetime.to_string(end_line),
                    'nb_resources': nb_resources,
                })
                current_day = self._next_working_day(last_day, wc)

        mo_start = preview_lines[0]['start'] if preview_lines else False
        mo_end = preview_lines[-1]['end'] if preview_lines else False
        po_data = self._get_related_purchase_orders_data()
        html = self._build_replan_preview_html(mo_start, mo_end, po_data)
        return {
            'summary_html': html,
            'data': {
                'mo_start': mo_start,
                'mo_end': mo_end,
                'lines': preview_lines,
                'po_data': po_data,
            }
        }

    def _build_replan_preview_html(self, mo_start, mo_end, po_data):
        po_items = ''.join(
            '<li>%s — livraison %s</li>' % (po['name'], po['date'])
            for po in po_data
        ) or '<li>Aucun PO lié trouvé</li>'
        return (
            '<div>'
            '<p><b>Nouvelle date début fabrication :</b> %s</p>'
            '<p><b>Nouvelle date fin fabrication :</b> %s</p>'
            '<p><b>PO liés :</b></p>'
            '<ul>%s</ul>'
            '<p>Valider pour appliquer les nouvelles dates, ou fermer pour annuler.</p>'
            '</div>'
        ) % (mo_start or '-', mo_end or '-', po_items)

    def _get_related_purchase_orders_data(self):
        self.ensure_one()
        po_lines = self.env['purchase.order.line']
        move_fields = ['purchase_line_id', 'created_purchase_line_id']
        for move in (self.move_raw_ids | self.move_finished_ids):
            for field_name in move_fields:
                if field_name in move._fields and move[field_name]:
                    po_lines |= move[field_name]
            if 'move_orig_ids' in move._fields:
                orig_moves = move.move_orig_ids
                for field_name in move_fields:
                    if field_name in orig_moves._fields:
                        po_lines |= orig_moves.mapped(field_name)
        orders = po_lines.mapped('order_id')
        result = []
        for po in orders:
            delivery = po.date_planned or po.date_approve or po.create_date
            result.append({
                'name': po.name,
                'date': fields.Datetime.to_string(delivery) if delivery else '-',
            })
        result.sort(key=lambda x: x['date'] or '')
        return result

    def action_apply_replan_preview(self, payload):
        self.ensure_one()
        for line in payload.get('lines', []):
            wo = self.env['mrp.workorder'].browse(line['wo_id']).exists()
            if not wo:
                continue
            vals = {
                'macro_planned_start': line['start'],
                'date_start': line['start'],
                'date_finished': line['end'],
            }
            if 'x_nb_resources' in wo._fields:
                vals['x_nb_resources'] = line.get('nb_resources', 1)
            wo.with_context(skip_shift_chain=True, skip_macro_recalc=True, mail_notrack=True).write(vals)

        vals = {}
        if payload.get('mo_start'):
            if 'date_start' in self._fields:
                vals['date_start'] = payload['mo_start']
            if 'date_planned_start' in self._fields:
                vals['date_planned_start'] = payload['mo_start']
        if payload.get('mo_end'):
            if 'date_finished' in self._fields:
                vals['date_finished'] = payload['mo_end']
            if 'date_planned_finished' in self._fields:
                vals['date_planned_finished'] = payload['mo_end']
            if 'date_deadline' in self._fields:
                vals['date_deadline'] = payload['mo_end']
        if vals:
            self.with_context(skip_macro_recalc=True, from_macro_update=True, mail_notrack=True).write(vals)
        if hasattr(self, '_update_components_picking_dates'):
            self._update_components_picking_dates()
        if hasattr(self, '_refresh_charge_cache_for_production'):
            self._refresh_charge_cache_for_production()
        return True
