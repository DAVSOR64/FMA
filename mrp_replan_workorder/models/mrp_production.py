# -*- coding: utf-8 -*-
import logging
from datetime import datetime, timedelta, time
from odoo import models, fields

_logger = logging.getLogger(__name__)

class MrpProduction(models.Model):
    _inherit = "mrp.production"

    # -----------------------------
    # ENTRY POINT (appelé depuis SO)
    # -----------------------------
    def _plan_mo_from_sale_order(self, sale_order):
        """
        Planifie l'OF selon la règle :
        - 1 opération par jour OUVRÉ pour cet OF
        - empilement sur chaque poste : 1 WO max / poste / jour
        - planification à rebours depuis la date promise du SO
        - date_start OF = date_start première opération
        """
        self.ensure_one()

        commitment_dt = sale_order.commitment_date
        if not commitment_dt:
            # fallback: tu peux décider une règle si pas de date promise
            # ex: date_order + 7 jours, ou rien -> forward
            _logger.info("SO %s sans commitment_date, fallback: forward via date_start ou now", sale_order.name)
            self._schedule_forward_stack()
            return

        _logger.info("Planif backward OF %s depuis SO %s (%s)",
                     self.name, sale_order.name, commitment_dt)

        self._schedule_backward_stack(commitment_dt)

    # ------------------------------------
    # BACKWARD: 1 OP / JOUR + EMPILAGE
    # ------------------------------------
    def _schedule_backward_stack(self, commitment_dt):
        self.ensure_one()

        workorders = self.workorder_ids.filtered(
            lambda w: w.state not in ['done', 'cancel']
        ).sorted('sequence', reverse=True)

        if not workorders:
            return

        # date cible (jour) = date promise
        current_day = fields.Datetime.to_datetime(commitment_dt).date()

        for idx, wo in enumerate(workorders):
            wc = wo.workcenter_id

            # on veut un "jour" pour cette opération
            # 1) trouver le dernier jour ouvré <= current_day (calendrier)
            day = self._get_previous_working_day(current_day + timedelta(days=1), wc)  # +1 pour inclure current_day

            # 2) empilement : si déjà occupé sur ce poste, reculer jusqu'à un jour libre
            day = self._find_previous_free_day_for_workcenter(day, wc)

            # 3) poser l'opération dans la journée (heure début = matin, fin = début + durée)
            start_dt = self._get_morning_datetime(day, wc)
            duration_min = wo.duration_expected or 0.0
            end_dt = start_dt + timedelta(minutes=duration_min)

            # Option sécurité: si la durée dépasse la journée, tu peux soit:
            # - tronquer à la fin de journée, soit
            # - pousser au lendemain (mais ça casse "1 op/jour")
            # Ici je garde simple : si dépasse, je cale à la fin de journée.
            evening = self._get_evening_datetime(day, wc)
            if end_dt > evening:
                end_dt = evening

            wo.write({'date_start': start_dt, 'date_finished': end_dt})

            _logger.info("✅ WO %s (%s) -> %s %s-%s",
                         wo.name, wc.name,
                         day.strftime('%Y-%m-%d'),
                         start_dt.strftime('%H:%M'),
                         end_dt.strftime('%H:%M'))

            # prochain WO (précédent dans la séquence) = la veille (en jours ouvrés)
            current_day = day - timedelta(days=1)

        self._update_production_dates_from_workorders()

    # ------------------------------------
    # FORWARD (fallback si pas de date)
    # ------------------------------------
    def _schedule_forward_stack(self):
        self.ensure_one()
        workorders = self.workorder_ids.filtered(
            lambda w: w.state not in ['done', 'cancel']
        ).sorted('sequence')

        if not workorders:
            return

        current_day = (self.date_start or fields.Datetime.now()).date()

        for idx, wo in enumerate(workorders):
            wc = wo.workcenter_id
            day = self._get_next_working_day(current_day, wc)
            day = self._find_next_free_day_for_workcenter(day, wc)

            start_dt = self._get_morning_datetime(day, wc)
            duration_min = wo.duration_expected or 0.0
            end_dt = start_dt + timedelta(minutes=duration_min)

            evening = self._get_evening_datetime(day, wc)
            if end_dt > evening:
                end_dt = evening

            wo.write({'date_start': start_dt, 'date_finished': end_dt})

            current_day = day + timedelta(days=1)

        self._update_production_dates_from_workorders()

    # -----------------------------
    # EMPILAGE: 1 WO / poste / jour
    # -----------------------------
    def _find_previous_free_day_for_workcenter(self, day, workcenter):
        """Recule tant qu'il y a déjà une WO sur ce workcenter ce jour-là."""
        max_iter = 90
        for _ in range(max_iter):
            if self._is_workcenter_free_on_day(workcenter, day):
                return day
            day = self._get_previous_working_day(day, workcenter)
        return day

    def _find_next_free_day_for_workcenter(self, day, workcenter):
        """Avance tant qu'il y a déjà une WO sur ce workcenter ce jour-là."""
        max_iter = 90
        for _ in range(max_iter):
            if self._is_workcenter_free_on_day(workcenter, day):
                return day
            day = self._get_next_working_day(day + timedelta(days=1), workcenter)
        return day

    def _is_workcenter_free_on_day(self, workcenter, day):
        """True si aucune WO (non done/cancel) n'est déjà planifiée sur ce poste ce jour."""
        start = datetime.combine(day, time.min)
        end = datetime.combine(day, time.max)

        existing = self.env['mrp.workorder'].search_count([
            ('workcenter_id', '=', workcenter.id),
            ('state', 'not in', ('done', 'cancel')),
            ('date_start', '<=', end),
            ('date_finished', '>=', start),
        ])
        return existing == 0

    # -----------------------------
    # CALENDRIER: jours ouvrés
    # -----------------------------
    def _get_next_working_day(self, from_date, workcenter):
        calendar = workcenter.resource_calendar_id or self.env.company.resource_calendar_id
        if not calendar:
            d = from_date
            while d.weekday() >= 5:
                d += timedelta(days=1)
            return d

        start_dt = datetime.combine(from_date, time.min)
        # plan_days(1) = prochain jour de travail (incluant congés/jours fériés)
        next_dt = calendar.plan_days(1.0, start_dt, compute_leaves=True)
        return (next_dt.date() if next_dt else from_date)

    def _get_previous_working_day(self, from_date, workcenter):
        calendar = workcenter.resource_calendar_id or self.env.company.resource_calendar_id
        if not calendar:
            d = from_date - timedelta(days=1)
            while d.weekday() >= 5:
                d -= timedelta(days=1)
            return d

        # on recule jour par jour jusqu’à trouver un jour avec des heures travaillées
        d = from_date - timedelta(days=1)
        for _ in range(90):
            start_dt = datetime.combine(d, time.min)
            end_dt = datetime.combine(d, time.max)
            intervals = calendar._work_intervals_batch(start_dt, end_dt)
            if intervals.get(False):
                return d
            d -= timedelta(days=1)
        return from_date - timedelta(days=1)

    def _get_morning_datetime(self, date, workcenter):
        calendar = workcenter.resource_calendar_id or self.env.company.resource_calendar_id
        start_hour = 8.0
        if calendar and calendar.attendance_ids:
            weekday = date.weekday()
            day_att = calendar.attendance_ids.filtered(lambda a: int(a.dayofweek) == weekday)
            if day_att:
                start_hour = day_att.sorted('hour_from')[0].hour_from

        h = int(start_hour)
        m = int((start_hour - h) * 60)
        return datetime.combine(date, time(h, m))

    def _get_evening_datetime(self, date, workcenter):
        calendar = workcenter.resource_calendar_id or self.env.company.resource_calendar_id
        end_hour = 17.0
        if calendar and calendar.attendance_ids:
            weekday = date.weekday()
            day_att = calendar.attendance_ids.filtered(lambda a: int(a.dayofweek) == weekday)
            if day_att:
                end_hour = day_att.sorted('hour_to')[-1].hour_to

        h = int(end_hour)
        m = int((end_hour - h) * 60)
        return datetime.combine(date, time(h, m))

    # -----------------------------
    # Update dates OF depuis WOs
    # -----------------------------
    def _update_production_dates_from_workorders(self):
        self.ensure_one()
        wos = self.workorder_ids.filtered(lambda w: w.state not in ['done', 'cancel'] and w.date_start and w.date_finished)
        if not wos:
            return

        first_wo = wos.sorted('date_start')[0]
        last_wo = wos.sorted('date_finished')[-1]

        self.write({
            'date_start': first_wo.date_start,
            'date_finished': last_wo.date_finished,
        })
