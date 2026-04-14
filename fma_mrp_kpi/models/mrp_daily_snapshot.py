# -*- coding: utf-8 -*-
import logging
from datetime import date, datetime, time, timedelta
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class MrpDailySnapshot(models.Model):
    _name = 'mrp.daily.snapshot'
    _description = 'Snapshot quotidien visu atelier'
    _order = 'snapshot_date desc, workcenter_id, production_id'
    _rec_name = 'display_name'

    snapshot_date = fields.Date(string='Date snapshot', required=True, index=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string='Poste de travail', required=True, index=True)
    workorder_id = fields.Many2one('mrp.workorder', string='Ordre de travail', required=True, index=True, ondelete='cascade')
    production_id = fields.Many2one('mrp.production', string='Ordre de fabrication', related='workorder_id.production_id', store=True)

    wo_name = fields.Char(string='Opération')
    mo_name = fields.Char(string='OF')
    state_at_eod = fields.Selection([
        ('pending', 'En attente'),
        ('waiting', 'En attente composants'),
        ('ready', 'Prêt'),
        ('progress', 'En cours'),
        ('done', 'Terminé'),
        ('cancel', 'Annulé'),
    ], string='État')

    macro_planned_start = fields.Datetime(string='Macro début prévue')
    macro_planned_finished = fields.Datetime(string='Macro fin prévue')

    duration_expected_h = fields.Float(string='Durée prévue (h)', digits=(10, 2))
    duration_real_h = fields.Float(string='Durée réelle (h)', digits=(10, 2))
    duration_expected_to_date_h = fields.Float(string='Théorique à date (h)', digits=(10, 2))

    delta_hours = fields.Float(string='Retard avancement (h)', digits=(10, 2), help='Retard d avancement cumulé de l OT à la date du snapshot. 0 = pas de retard.')
    is_late = fields.Boolean(string='En retard')
    is_done = fields.Boolean(string='Terminé')
    capture_reason = fields.Selection([
        ('planned_today', 'Prévu aujourd hui'),
        ('carry_over', 'Glissement'),
        ('future', 'À venir'),
    ], string='Raison')
    cumul_retard_wc = fields.Float(string='Retard cumulé poste (h)', digits=(10, 2))

    display_name = fields.Char(string='Libellé', compute='_compute_display_name', store=True)

    @api.depends('snapshot_date', 'workcenter_id', 'wo_name')
    def _compute_display_name(self):
        for rec in self:
            date_str = rec.snapshot_date.strftime('%d/%m/%Y') if rec.snapshot_date else '-'
            wc = rec.workcenter_id.name or '-'
            wo = rec.wo_name or '-'
            rec.display_name = f"{date_str} | {wc} | {wo}"

    _sql_constraints = [
        ('unique_snapshot_wo_date', 'UNIQUE(snapshot_date, workorder_id)', 'Un seul snapshot par OT et par journée.'),
    ]

    @api.model
    def cron_compute_daily_snapshot(self):
        today = fields.Date.context_today(self)
        now_dt = fields.Datetime.now()

        _logger.info('=' * 60)
        _logger.info('VISU ATELIER START : %s | now=%s', today, now_dt)
        _logger.info('=' * 60)

        existing = self.search([('snapshot_date', '=', today)])
        if existing:
            existing.unlink()

        eligible_wos = self._get_eligible_workorders(today)
        _logger.info('VISU ATELIER : %d OTs éligibles trouvés', len(eligible_wos))

        vals_list = []
        for wo in eligible_wos:
            vals = self._compute_snapshot_vals(wo, today, now_dt)
            if vals:
                vals_list.append(vals)

        if vals_list:
            self.create(vals_list)

        self._compute_cumul_retard(today)

        _logger.info('VISU ATELIER END : %d snapshots créés', len(vals_list))
        _logger.info('=' * 60)

    @api.model
    def _get_eligible_workorders(self, today):
        MrpWO = self.env['mrp.workorder']
        start_day = datetime.combine(today, time.min)
        domain = [
            ('state', 'not in', ['cancel']),
            ('macro_planned_start', '!=', False),
            '|',
            ('macro_planned_start', '<=', start_day + timedelta(days=1, seconds=-1)),
            '&', ('state', '=', 'done'), ('date_finished', '>=', start_day),
        ]
        return MrpWO.search(domain)

    @api.model
    def _planned_finish_for_wo(self, wo, duration_expected_h):
        finish = getattr(wo, 'macro_planned_finished', False)
        if finish:
            return finish
        if wo.macro_planned_start:
            return wo.macro_planned_start + timedelta(hours=duration_expected_h or 0.0)
        return False

    @api.model
    def _expected_hours_to_date(self, start_dt, finish_dt, planned_hours, now_dt):
        if not start_dt or planned_hours <= 0:
            return 0.0
        if not finish_dt or finish_dt <= start_dt:
            finish_dt = start_dt + timedelta(hours=planned_hours)
        if now_dt <= start_dt:
            return 0.0
        if now_dt >= finish_dt:
            return planned_hours
        total_seconds = max((finish_dt - start_dt).total_seconds(), 1.0)
        elapsed_seconds = max((now_dt - start_dt).total_seconds(), 0.0)
        return min(planned_hours, planned_hours * (elapsed_seconds / total_seconds))

    @api.model
    def _compute_snapshot_vals(self, wo, today, now_dt):
        duration_expected_h = (wo.duration_expected or 0.0) / 60.0
        duration_real_h = (wo.duration or 0.0) / 60.0

        macro_start = wo.macro_planned_start
        macro_finish = self._planned_finish_for_wo(wo, duration_expected_h)
        is_done = wo.state == 'done'

        if macro_start and macro_start.date() == today:
            reason = 'planned_today'
        else:
            reason = 'carry_over'

        expected_to_date_h = self._expected_hours_to_date(macro_start, macro_finish, duration_expected_h, now_dt)

        delay_h = 0.0
        if is_done:
            actual_finish = wo.date_finished or now_dt
            if macro_finish and actual_finish and actual_finish > macro_finish:
                delay_h = max(duration_expected_h - duration_real_h, 0.0)
                # si temps réel < prévu mais fini après la cible, on garde au moins un petit retard temporel
                if delay_h == 0.0:
                    delay_h = max((actual_finish - macro_finish).total_seconds() / 3600.0, 0.0)
            else:
                delay_h = 0.0
        else:
            delay_h = max(expected_to_date_h - duration_real_h, 0.0)

        is_late = delay_h > 0.0001

        _logger.info(
            'VISU | OT %s | poste=%s | état=%s | macro_start=%s | macro_finish=%s | prévu=%.2fh | théorique=%.2fh | réel=%.2fh | retard=%.2fh',
            wo.name,
            wo.workcenter_id.name,
            wo.state,
            macro_start,
            macro_finish,
            duration_expected_h,
            expected_to_date_h,
            duration_real_h,
            delay_h,
        )

        return {
            'snapshot_date': today,
            'workcenter_id': wo.workcenter_id.id,
            'workorder_id': wo.id,
            'wo_name': wo.name,
            'mo_name': wo.production_id.name if wo.production_id else '',
            'state_at_eod': wo.state,
            'macro_planned_start': macro_start,
            'macro_planned_finished': macro_finish,
            'duration_expected_h': duration_expected_h,
            'duration_real_h': duration_real_h,
            'duration_expected_to_date_h': expected_to_date_h,
            'delta_hours': delay_h,
            'is_late': is_late,
            'is_done': is_done,
            'capture_reason': reason,
            'cumul_retard_wc': 0.0,
        }

    @api.model
    def _compute_cumul_retard(self, today):
        today_snaps = self.search([('snapshot_date', '=', today)])
        wc_ids = today_snaps.mapped('workcenter_id').ids
        for wc_id in wc_ids:
            self.env.cr.execute(
                """
                SELECT COALESCE(SUM(delta_hours), 0)
                FROM mrp_daily_snapshot
                WHERE workcenter_id = %s
                  AND snapshot_date <= %s
                  AND delta_hours > 0
                """,
                (wc_id, today),
            )
            row = self.env.cr.fetchone()
            cumul = float(row[0] or 0.0) if row else 0.0
            today_snaps.filtered(lambda s: s.workcenter_id.id == wc_id).write({'cumul_retard_wc': cumul})

    @api.model
    def action_recompute_today(self):
        self.cron_compute_daily_snapshot()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Visu Atelier recalculée'),
                'message': _('Le snapshot du jour a été recalculé avec succès.'),
                'type': 'success',
                'sticky': False,
            }
        }
